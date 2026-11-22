"""Ritmo: launch pace spikes (STA/LTA), slow format drift (CUSUM), and Little's Law.

All calculations use Python's standard library only and operate per concept for a
single advertiser page (`mode == "company"`). Everything fails closed when data
is a keyword sample, a partial list, or lacks history:

* **STA/LTA (1w vs prior 8w):** compares the latest complete 7-day rolling window
  ending on ``as_of`` against the prior 8 complete 7-day windows, evaluated with
  an exact log-space binomial tail test and stricter thresholds when only active
  ads are observed (survivor bias guard).
* **Format CUSUM:** two-sided standardized Page CUSUM across chronological concept
  launches after splitting the observed span in half, flagging sustained mix shifts
  with a materiality floor and change-point date.
* **Little's Law (``L = λW``):** links currently active concepts ``L`` and recent
  28-day launch velocity ``λ`` to implied lifespan, cross-checked against ``Durata``
  RMST when cohort survival has been loaded.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

COMPLETE_SHARE = 0.9

STA_DAYS = 7
LTA_WEEKS = 8
MIN_LTA_TOTAL = 4

MIN_SPIKE_COUNT_ACTIVE = 5
MIN_SPIKE_RATIO_ACTIVE = 2.5
MAX_SPIKE_P_ACTIVE = 0.01

MIN_SPIKE_COUNT_FULL = 4
MIN_SPIKE_RATIO_FULL = 2.0
MAX_SPIKE_P_FULL = 0.02

MAX_SLOWDOWN_RATIO = 0.4
MIN_SLOWDOWN_LTA_MEAN = 2.0
MAX_SLOWDOWN_P = 0.05

MIN_CUSUM_CONCEPTS = 16
MIN_CUSUM_SPAN_DAYS = 14
CUSUM_K = 0.25
CUSUM_H = 4.0
CUSUM_SIGMA_FLOOR = 0.30
CUSUM_MIN_DELTA = 0.15
CUSUM_MIN_EXCESS = 2.5

LITTLE_WINDOW_DAYS = 28
MIN_LITTLE_ACTIVE = 5
MIN_LITTLE_LAUNCHES = 2


def _parse_day(raw) -> date | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _parse_dt(raw) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        d = _parse_day(text)
        if d is None:
            return None
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ad_ids(ad: dict) -> set[str]:
    out: set[str] = set()
    if ad.get("library_id"):
        out.add(str(ad["library_id"]))
    for field in ("ids", "variant_ids", "collation_ids"):
        for item in ad.get(field) or ():
            if item:
                out.add(str(item))
    for member in ad.get("members") or ():
        if isinstance(member, dict) and member.get("library_id"):
            out.add(str(member["library_id"]))
    return out


def _binom_pmf(n: int, k: int, p: float) -> float:
    """Numerically stable Binomial(n, p) PMF in log space via ``math.lgamma``."""
    if n < 0 or k < 0 or k > n:
        return 0.0
    if p <= 0.0:
        return 1.0 if k == 0 else 0.0
    if p >= 1.0:
        return 1.0 if k == n else 0.0
    log_c = math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    log_val = log_c + k * math.log(p) + (n - k) * math.log1p(-p)
    if log_val < -745.0:
        return 0.0
    return min(1.0, max(0.0, math.exp(log_val)))


def _binom_upper_tail(n: int, k: int, p: float) -> float:
    """Exact ``P(X >= k)`` for ``X ~ Binomial(n, p)``."""
    if k <= 0:
        return 1.0
    if k > n or n <= 0:
        return 0.0
    total = 0.0
    mean = n * p
    for i in range(k, n + 1):
        term = _binom_pmf(n, i, p)
        total += term
        if i > mean + 5.0 and term < 1e-15 * max(total, 1e-12):
            break
    return min(max(total, 0.0), 1.0)


def _binom_lower_tail(n: int, k: int, p: float) -> float:
    """Exact ``P(X <= k)`` for ``X ~ Binomial(n, p)``."""
    if k < 0:
        return 0.0
    if n <= 0 or k >= n:
        return 1.0
    total = 0.0
    mean = n * p
    for i in range(k, -1, -1):
        term = _binom_pmf(n, i, p)
        total += term
        if i < mean - 5.0 and term < 1e-15 * max(total, 1e-12):
            break
    return min(max(total, 0.0), 1.0)


def merge_snapshot_concepts(snapshots: list[dict]) -> tuple[list[dict], list[dict], int]:
    """Deduplicate concepts across saved snapshots, preserving stopped concepts too."""
    ordered = sorted(
        (s for s in snapshots if s and s.get("ads") is not None),
        key=lambda s: str(s.get("taken_at") or ""),
    )
    if not ordered:
        return [], [], 0

    records: list[dict] = []
    id_to_idx: dict[str, int] = {}
    last_idx = len(ordered) - 1

    for snap_idx, snap in enumerate(ordered):
        for ad in snap.get("ads") or []:
            ids = _ad_ids(ad)
            matched = sorted({id_to_idx[i] for i in ids if i in id_to_idx})
            started = _parse_day(ad.get("started"))
            media_type = (ad.get("media_type") or "").strip().casefold() or None
            if not matched:
                idx = len(records)
                records.append({
                    "library_id": ad.get("library_id") or (sorted(ids)[0] if ids else ""),
                    "ids": set(ids),
                    "_started": started,
                    "started": started.isoformat() if started else ad.get("started"),
                    "ended": ad.get("ended"),
                    "media_type": media_type,
                    "days_running": ad.get("days_running"),
                    "_last_snap": snap_idx,
                    "_raw_status": ad.get("status"),
                })
            else:
                idx = matched[0]
                rec = records[idx]
                rec["ids"].update(ids)
                if started and (rec["_started"] is None or started < rec["_started"]):
                    rec["_started"] = started
                    rec["started"] = started.isoformat()
                if media_type and (media_type != "unknown" or not rec["media_type"]):
                    rec["media_type"] = media_type
                if ad.get("library_id"):
                    rec["library_id"] = ad["library_id"]
                if ad.get("days_running") is not None:
                    rec["days_running"] = ad["days_running"]
                if ad.get("ended"):
                    rec["ended"] = ad["ended"]
                rec["_last_snap"] = snap_idx
                rec["_raw_status"] = ad.get("status")
                for extra_idx in matched[1:]:
                    extra = records[extra_idx]
                    rec["ids"].update(extra["ids"])
                    if extra["_started"] and (rec["_started"] is None or extra["_started"] < rec["_started"]):
                        rec["_started"] = extra["_started"]
                        rec["started"] = extra["started"]
                    extra["_merged_into"] = idx
            for i in records[idx]["ids"]:
                id_to_idx[i] = idx

    union_concepts: list[dict] = []
    for rec in records:
        if "_merged_into" in rec:
            continue
        is_active = rec["_last_snap"] == last_idx and rec.get("_raw_status") != "inactive"
        union_concepts.append({
            "library_id": rec["library_id"],
            "ids": sorted(rec["ids"]),
            "started": rec["started"],
            "ended": rec.get("ended"),
            "media_type": rec["media_type"] or "unknown",
            "days_running": rec.get("days_running"),
            "status": "active" if is_active else "inactive",
        })

    series: list[dict] = []
    for snap in ordered[-12:]:
        ads_list = snap.get("ads") or []
        n_c = len(ads_list)
        v_count = sum(1 for a in ads_list if (a.get("media_type") or "").casefold() == "video")
        i_count = sum(1 for a in ads_list if (a.get("media_type") or "").casefold() == "image")
        series.append({
            "taken_at": snap.get("taken_at"),
            "active_ads": snap.get("active_ads"),
            "concepts": n_c,
            "video_share": round(v_count / n_c, 2) if n_c else 0.0,
            "image_share": round(i_count / n_c, 2) if n_c else 0.0,
        })

    dt_first = _parse_dt(ordered[0].get("taken_at"))
    dt_last = _parse_dt(ordered[-1].get("taken_at"))
    span_days = max(0, int((dt_last - dt_first).total_seconds() // 86400)) if dt_first and dt_last else 0
    return union_concepts, series, span_days


def sta_lta(concepts: list[dict], *, as_of: date, survivor_bias: bool = True) -> dict:
    """Compare latest 7-day concept launches (STA) vs prior 8 weeks (LTA)."""
    min_count = MIN_SPIKE_COUNT_ACTIVE if survivor_bias else MIN_SPIKE_COUNT_FULL
    min_ratio = MIN_SPIKE_RATIO_ACTIVE if survivor_bias else MIN_SPIKE_RATIO_FULL
    max_p = MAX_SPIKE_P_ACTIVE if survivor_bias else MAX_SPIKE_P_FULL

    buckets: list[list[tuple[date, str]]] = [[] for _ in range(LTA_WEEKS + 1)]
    for c in concepts:
        started = _parse_day(c.get("started"))
        if started is None or started > as_of:
            continue
        age_days = (as_of - started).days
        if age_days >= (LTA_WEEKS + 1) * STA_DAYS:
            continue
        w_back = age_days // STA_DAYS
        idx = LTA_WEEKS - w_back
        buckets[idx].append((started, str(c.get("library_id") or "")))

    weeks = []
    for idx in range(LTA_WEEKS + 1):
        w_back = LTA_WEEKS - idx
        end_d = as_of - timedelta(days=w_back * STA_DAYS)
        start_d = end_d - timedelta(days=STA_DAYS - 1)
        weeks.append({
            "week_start": start_d.isoformat(),
            "week_end": end_d.isoformat(),
            "concepts": len(buckets[idx]),
            "is_sta": w_back == 0,
        })

    recent_ids = [
        lib_id for _, lib_id in sorted(buckets[-1], key=lambda item: (-item[0].toordinal(), item[1]))
        if lib_id
    ][:5]
    sta_count = weeks[-1]["concepts"]
    lta_total = sum(w["concepts"] for w in weeks[:-1])
    lta_mean = round(lta_total / float(LTA_WEEKS), 2)
    total_63d = sta_count + lta_total
    p_week = 1.0 / (LTA_WEEKS + 1)
    p_surge = round(_binom_upper_tail(total_63d, sta_count, p_week), 4) if total_63d > 0 else 1.0
    p_slow = round(_binom_lower_tail(total_63d, sta_count, p_week), 4) if total_63d > 0 else 1.0

    base = {
        "sta_count": sta_count,
        "lta_total": lta_total,
        "lta_mean": lta_mean,
        "weeks": weeks,
        "recent_ids": recent_ids,
        "survivor_bias_caveat": survivor_bias,
        "p_surge": p_surge,
        "p_slow": p_slow,
    }
    if lta_total < MIN_LTA_TOTAL:
        if sta_count >= min_count and p_surge <= max_p:
            return {
                **base,
                "measurable": True,
                "state": "spike",
                "ratio": None,
                "p_value": p_surge,
                "burst_from_zero": True,
                "trigger_ai": True,
            }
        return {
            **base,
            "measurable": False,
            "reason": "too_few_launches",
            "ratio": None,
            "p_value": p_surge,
            "trigger_ai": False,
        }

    exact_ratio = sta_count / (lta_total / float(LTA_WEEKS))
    ratio = round(exact_ratio, 2)
    if exact_ratio >= min_ratio and sta_count >= min_count and p_surge <= max_p:
        state, p_value, trigger_ai = "spike", p_surge, True
    elif (exact_ratio <= MAX_SLOWDOWN_RATIO
          and (lta_total / float(LTA_WEEKS)) >= MIN_SLOWDOWN_LTA_MEAN
          and p_slow <= MAX_SLOWDOWN_P):
        state, p_value, trigger_ai = "slowdown", p_slow, False
    elif exact_ratio >= 1.5 and sta_count >= 3:
        state, p_value, trigger_ai = "elevated", p_surge, False
    else:
        state, p_value, trigger_ai = "steady", p_surge, False

    return {
        **base,
        "measurable": True,
        "state": state,
        "ratio": ratio,
        "p_value": p_value,
        "trigger_ai": trigger_ai,
    }


def format_cusum(concepts: list[dict], *, as_of: date) -> dict:
    """Detect sustained slow drift in creative format mix with two-sided Page CUSUM."""
    dated: list[tuple[date, str, dict]] = []
    for c in concepts:
        started = _parse_day(c.get("started"))
        fmt = (c.get("media_type") or "").strip().casefold()
        if started is None or started > as_of or not fmt or fmt == "unknown":
            continue
        dated.append((started, fmt, c))

    if len(dated) < MIN_CUSUM_CONCEPTS:
        return {
            "measurable": False,
            "reason": "too_few_concepts",
            "concepts": len(dated),
            "span_days": 0,
            "drift_detected": False,
            "trigger_ai": False,
        }

    ordered = sorted(dated, key=lambda row: (row[0], str(row[2].get("library_id") or "")))
    span_days = (ordered[-1][0] - ordered[0][0]).days
    if span_days < MIN_CUSUM_SPAN_DAYS:
        return {
            "measurable": False,
            "reason": "short_span",
            "concepts": len(ordered),
            "span_days": span_days,
            "drift_detected": False,
            "trigger_ai": False,
        }

    mid = len(ordered) // 2
    if ordered[mid - 1][0] == ordered[mid][0]:
        min_side = max(4, MIN_CUSUM_CONCEPTS // 4)
        candidates = [
            i for i in range(min_side, len(ordered) - min_side + 1)
            if ordered[i - 1][0] < ordered[i][0]
        ]
        if not candidates:
            return {
                "measurable": False,
                "reason": "clustered_dates",
                "concepts": len(ordered),
                "span_days": span_days,
                "drift_detected": False,
                "trigger_ai": False,
            }
        mid = min(candidates, key=lambda i: (abs(i - mid), i))
    baseline = ordered[:mid]
    recent = ordered[mid:]
    split_date = recent[0][0].isoformat()

    counts: dict[str, int] = {}
    for _, fmt, _ in ordered:
        counts[fmt] = counts.get(fmt, 0) + 1
    distinct_formats = [k for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    formats_out: list[dict] = []
    for fmt in distinct_formats:
        base_count = sum(1 for _, f, _ in baseline if f == fmt)
        rec_count = sum(1 for _, f, _ in recent if f == fmt)
        p0 = base_count / float(len(baseline))
        p1 = rec_count / float(len(recent))
        delta = round(p1 - p0, 4)
        sigma = max(math.sqrt(max(0.0, p0 * (1.0 - p0))), CUSUM_SIGMA_FLOOR)

        c_pos = 0.0
        c_neg = 0.0
        max_pos = 0.0
        max_neg = 0.0
        pos_start: date | None = None
        neg_start: date | None = None
        pos_cp: str | None = None
        neg_cp: str | None = None

        for d_i, f_i, _ in recent:
            x = 1.0 if f_i == fmt else 0.0
            z = (x - p0) / sigma

            prev_pos = c_pos
            c_pos = max(0.0, c_pos + z - CUSUM_K)
            if c_pos > 0.0 and prev_pos == 0.0:
                pos_start = d_i
            elif c_pos == 0.0:
                pos_start = None
            if c_pos > max_pos:
                max_pos = c_pos
            if pos_cp is None and c_pos >= CUSUM_H:
                pos_cp = (pos_start or d_i).isoformat()

            prev_neg = c_neg
            c_neg = max(0.0, c_neg - z - CUSUM_K)
            if c_neg > 0.0 and prev_neg == 0.0:
                neg_start = d_i
            elif c_neg == 0.0:
                neg_start = None
            if c_neg > max_neg:
                max_neg = c_neg
            if neg_cp is None and c_neg >= CUSUM_H:
                neg_cp = (neg_start or d_i).isoformat()

        excess = abs(rec_count - p0 * len(recent))
        if max_pos >= CUSUM_H and delta >= CUSUM_MIN_DELTA and excess >= CUSUM_MIN_EXCESS:
            direction, peak, cp_date = "up", round(max_pos, 2), pos_cp
        elif max_neg >= CUSUM_H and delta <= -CUSUM_MIN_DELTA and excess >= CUSUM_MIN_EXCESS:
            direction, peak, cp_date = "down", round(max_neg, 2), neg_cp
        else:
            direction, peak, cp_date = "steady", round(max(max_pos, max_neg), 2), None

        formats_out.append({
            "format": fmt,
            "baseline_share": round(p0, 3),
            "recent_share": round(p1, 3),
            "delta_share": delta,
            "baseline_count": base_count,
            "recent_count": rec_count,
            "cusum_peak": peak,
            "threshold": CUSUM_H,
            "direction": direction,
            "changepoint_date": cp_date,
        })

    drifting = [row for row in formats_out if row["direction"] != "steady"]
    if drifting:
        primary = max(drifting, key=lambda r: (abs(r["delta_share"]), r["cusum_peak"]))
    else:
        primary = next((r for r in formats_out if r["format"] == "video"), formats_out[0])

    drift_detected = bool(drifting)
    rising = [r for r in drifting if r["direction"] == "up"]
    target_fmt = (
        primary["format"] if primary["direction"] == "up"
        else rising[0]["format"] if rising
        else primary["format"]
    )
    example_ids = [
        str(c["library_id"])
        for _, f, c in reversed(recent)
        if f == target_fmt and c.get("library_id")
    ][:3]
    if not example_ids and drifting:
        example_ids = [str(c["library_id"]) for _, _, c in reversed(recent) if c.get("library_id")][:3]

    return {
        "measurable": True,
        "concepts": len(ordered),
        "baseline_n": len(baseline),
        "recent_n": len(recent),
        "span_days": span_days,
        "split_date": split_date,
        "drift_detected": drift_detected,
        "trigger_ai": drift_detected,
        "primary": primary,
        "formats": formats_out,
        "example_ids": example_ids,
    }


def littles_law(active_concepts: list[dict], all_concepts: list[dict], *,
                as_of: date, durata_report: dict | None = None) -> dict:
    """Link active inventory ``L`` and launch rate ``λ`` via ``L = λW``."""
    L = len(active_concepts)
    if L < MIN_LITTLE_ACTIVE:
        return {"measurable": False, "reason": "too_few_active", "active_concepts": L}

    launches_28d = 0
    for c in all_concepts:
        started = _parse_day(c.get("started"))
        if started is not None and 0 <= (as_of - started).days < LITTLE_WINDOW_DAYS:
            launches_28d += 1
    if launches_28d < MIN_LITTLE_LAUNCHES:
        return {
            "measurable": False,
            "reason": "too_few_launches",
            "active_concepts": L,
            "launches_28d": launches_28d,
            "window_days": LITTLE_WINDOW_DAYS,
        }

    lambda_per_day = launches_28d / float(LITTLE_WINDOW_DAYS)
    lambda_per_week = round(lambda_per_day * 7.0, 2)
    implied_mean_days = round(L / lambda_per_day, 1)

    ages: list[int] = []
    for c in active_concepts:
        started = _parse_day(c.get("started"))
        if started is not None and started <= as_of:
            ages.append(max(1, (as_of - started).days))
        elif c.get("days_running") is not None:
            ages.append(max(1, int(c["days_running"])))
    active_mean_age_days = round(sum(ages) / len(ages), 1) if ages else None

    if durata_report and durata_report.get("available") and (durata_report.get("rmst_days") or 0) > 0:
        w_days = round(float(durata_report["rmst_days"]), 1)
        expected_active = round(lambda_per_day * float(durata_report["rmst_days"]), 1)
        balance_ratio = round(L / expected_active, 2) if expected_active > 0 else None
        if balance_ratio is not None and balance_ratio > 1.35:
            balance_state = "accumulating"
        elif balance_ratio is not None and balance_ratio < 0.70:
            balance_state = "ramping_or_cutting"
        else:
            balance_state = "balanced"
        steady_state_checked = True
        w_source = "durata_rmst"
    else:
        w_days = None
        expected_active = None
        balance_ratio = None
        balance_state = "implied_only"
        steady_state_checked = False
        w_source = "implied_only"

    return {
        "measurable": True,
        "active_concepts": L,
        "launches_28d": launches_28d,
        "window_days": LITTLE_WINDOW_DAYS,
        "lambda_per_day": round(lambda_per_day, 3),
        "lambda_per_week": lambda_per_week,
        "implied_mean_days": implied_mean_days,
        "active_mean_age_days": active_mean_age_days,
        "steady_state_checked": steady_state_checked,
        "w_source": w_source,
        "mean_duration_days": w_days,
        "expected_active": expected_active,
        "balance_ratio": balance_ratio,
        "balance_state": balance_state,
    }


def _combine_live_and_snapshots(concepts: list[dict], snapshots: list[dict]) -> tuple[list[dict], list[dict], int]:
    union_concepts, series, span_days = merge_snapshot_concepts(snapshots)
    if not concepts:
        return union_concepts, series, span_days
    known_ids = {i for c in union_concepts for i in _ad_ids(c)}
    merged = list(union_concepts)
    for c in concepts:
        ids = _ad_ids(c)
        if not ids or not (ids & known_ids):
            merged.append(c)
            known_ids.update(ids)
    return merged, series, span_days


def analyze(concepts: list[dict], *, mode: str = "company", loaded_share: float | None = None,
            as_of: date | None = None, snapshots: list[dict] | None = None,
            durata_report: dict | None = None, active_status: str = "active") -> dict:
    """Compute full ``Ritmo`` diagnostics when quality and completeness gates pass."""
    as_of = as_of or date.today()
    snap_list = [s for s in (snapshots or []) if s and s.get("ads") is not None]
    base = {
        "available": False,
        "unit": "concept",
        "mode": mode,
        "loaded_share": loaded_share,
        "as_of": as_of.isoformat(),
        "snapshots": len(snap_list),
        "trigger_ai": False,
        "alerts": [],
    }
    if mode != "company":
        return {**base, "reason": "keyword_mode"}
    if loaded_share is not None and loaded_share < COMPLETE_SHARE:
        return {**base, "reason": "partial_list"}

    if len(snap_list) >= 2:
        all_concepts, snapshot_series, span_days = _combine_live_and_snapshots(concepts, snap_list)
        active_source = concepts if concepts else all_concepts
        active_concepts = [c for c in active_source if c.get("status") != "inactive" and not c.get("ended")]
    else:
        all_concepts = list(concepts)
        _, snapshot_series, span_days = merge_snapshot_concepts(snap_list)
        active_concepts = [c for c in all_concepts if c.get("status") != "inactive" and not c.get("ended")]

    survivor_bias = active_status != "all" and span_days < 21
    if active_status == "all":
        source = "cohort_all"
    elif len(snap_list) >= 2 and span_days >= 21:
        source = "snapshots"
    elif len(snap_list) >= 2:
        source = "snapshots_short"
    else:
        source = "active_only"

    st = sta_lta(all_concepts, as_of=as_of, survivor_bias=survivor_bias)
    cu = format_cusum(all_concepts, as_of=as_of)
    lt = littles_law(active_concepts, all_concepts, as_of=as_of, durata_report=durata_report)

    if not any((st.get("measurable"), cu.get("measurable"), lt.get("measurable"))):
        return {
            **base,
            "reason": "insufficient_history",
            "source": source,
            "survivor_bias": survivor_bias,
            "snapshot_span_days": span_days,
            "sta_lta": st,
            "cusum": cu,
            "littles_law": lt,
            "snapshot_series": snapshot_series,
        }

    alerts: list[str] = []
    if st.get("trigger_ai"):
        alerts.append("launch_spike")
    if cu.get("trigger_ai"):
        alerts.append("format_drift")
    trigger_ai = bool(alerts)

    if trigger_ai:
        status = "alert"
    elif st.get("state") == "slowdown":
        status = "slowdown"
    elif st.get("state") == "elevated":
        status = "elevated"
    else:
        status = "steady"

    return {
        **base,
        "available": True,
        "source": source,
        "survivor_bias": survivor_bias,
        "snapshot_span_days": span_days,
        "status": status,
        "trigger_ai": trigger_ai,
        "alerts": alerts,
        "sta_lta": st,
        "cusum": cu,
        "littles_law": lt,
        "snapshot_series": snapshot_series,
    }


def analyze_snapshots(snapshots: list[dict], *, durata_report: dict | None = None,
                      as_of: date | None = None) -> dict:
    """Compute ``Ritmo`` directly from saved ``History`` snapshots."""
    ordered = sorted(
        (s for s in snapshots if s and s.get("ads") is not None),
        key=lambda s: str(s.get("taken_at") or ""),
    )
    if not ordered:
        return {
            "available": False,
            "reason": "no_snapshots",
            "trigger_ai": False,
            "alerts": [],
            "snapshots": 0,
        }
    latest = ordered[-1]
    subj = latest.get("subject") or {}
    snap_as_of = as_of or _parse_day(latest.get("taken_at")) or date.today()
    return analyze(
        latest.get("ads") or [],
        mode=subj.get("mode", "company"),
        loaded_share=latest.get("loaded_share"),
        as_of=snap_as_of,
        snapshots=ordered,
        durata_report=durata_report,
        active_status="active",
    )


def format_summary(report: dict) -> list[str]:
    """Concise 5-8 line text block strictly for ``testing.md`` (never ``overview.md``)."""
    share = report.get("loaded_share")
    share_label = f"{round(share * 100)}%" if share is not None else "n/a"

    if not report.get("available"):
        reason = report.get("reason") or "unavailable"
        reasons = {
            "keyword_mode": "a keyword search loads a sample across advertisers, not one company list",
            "partial_list": f"the list was read in part (loaded share {share_label})",
            "insufficient_history": "too few dated concepts across recent weeks and formats",
            "no_snapshots": "no saved snapshots exist yet for this subject",
        }
        detail = reasons.get(reason, str(reason))
        return [
            f"- Pace and format drift (Ritmo): not available ({reason}). Reason: {detail}.",
            "- Do not state a launch surge or format shift without a measured baseline here.",
        ]

    ai_flag = "yes" if report.get("trigger_ai") else "no"
    alerts = ", ".join(report.get("alerts") or []) or "none"
    lines = [
        f"- Ritmo scope: unit = concept, source = {report.get('source', 'active_only')}, "
        f"loaded share {share_label}, snapshots = {report.get('snapshots', 0)} "
        f"(AI alert: {ai_flag}; triggers: {alerts}).",
    ]

    st = report.get("sta_lta") or {}
    if st.get("measurable"):
        state = st.get("state", "steady")
        ratio_txt = f"{st['ratio']}x" if st.get("ratio") is not None else "burst from near-zero"
        caveat = " (active-only survivor-bias caveat applies)" if st.get("survivor_bias_caveat") else ""
        ids_txt = (
            "; recent ids: " + ", ".join(f"id {i}" for i in st["recent_ids"][:4])
            if (st.get("trigger_ai") and st.get("recent_ids")) else ""
        )
        lines.append(
            f"- Launch pace (STA/LTA, 1w vs prior 8w): {state} ({ratio_txt}; "
            f"last 7d = {st['sta_count']} vs {st['lta_mean']}/wk prior 8w, p = {st['p_value']}){caveat}{ids_txt}."
        )
    else:
        lines.append(
            f"- Launch pace (STA/LTA, 1w vs prior 8w): not available ({st.get('reason', 'too_few_launches')}; "
            f"last 7d = {st.get('sta_count', 0)}, prior 8w total = {st.get('lta_total', 0)})."
        )

    cu = report.get("cusum") or {}
    if cu.get("measurable"):
        prim = cu.get("primary") or {}
        if cu.get("drift_detected") and prim:
            cp = f" near {prim['changepoint_date']}" if prim.get("changepoint_date") else ""
            ids_txt = (
                "; examples: " + ", ".join(f"id {i}" for i in cu.get("example_ids", [])[:3])
                if cu.get("example_ids") else ""
            )
            lines.append(
                f"- Format drift (CUSUM): {prim['format']} shifted {prim['direction']} from "
                f"{round(prim['baseline_share'] * 100)}% to {round(prim['recent_share'] * 100)}% "
                f"(peak {prim['cusum_peak']} vs H={prim['threshold']}, split {cu['split_date']}{cp}){ids_txt}."
            )
        else:
            fmt_txt = (
                f" ({prim['format']} {round(prim['baseline_share'] * 100)}% -> {round(prim['recent_share'] * 100)}%, "
                f"peak {prim['cusum_peak']} < H={prim['threshold']})"
                if prim else ""
            )
            lines.append(f"- Format drift (CUSUM): steady across {cu['concepts']} concepts over {cu['span_days']}d{fmt_txt}.")
    else:
        lines.append(f"- Format drift (CUSUM): not available ({cu.get('reason', 'too_few_concepts')}).")

    lt = report.get("littles_law") or {}
    if lt.get("measurable"):
        extra = (
            f"; vs Durata RMST {lt['mean_duration_days']}d -> expected {lt['expected_active']} active "
            f"(ratio {lt['balance_ratio']}x, {lt['balance_state']})"
            if lt.get("steady_state_checked")
            else "; implied turnover only (no cohort Durata)"
        )
        lines.append(
            f"- Portfolio balance (Little's Law, L = λW): L = {lt['active_concepts']} active concepts, "
            f"λ = {lt['lambda_per_week']}/wk (28d), implied mean life {lt['implied_mean_days']}d{extra}."
        )
    else:
        lines.append(
            f"- Portfolio balance (Little's Law, L = λW): not available ({lt.get('reason', 'too_few_active')})."
        )

    lines.append(
        "- Note: Ritmo measures publishing cadence and format mix, never spend, profit or ROAS; "
        "check seasonal launches or batch releases before acting."
    )
    return lines
