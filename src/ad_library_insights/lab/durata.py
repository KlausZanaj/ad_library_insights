"""Durata: cohort survival analysis per ad concept using pure Python stdlib.

When both active and inactive ads of one advertiser page are loaded in full for a
look-back window, concepts are treated as right-censored observations:

* Kaplan-Meier product-limit survival curve with Greenwood standard errors,
  log-log 95% confidence intervals, exact median lifespan and restricted mean
  survival time (RMST).
* Right-censored Weibull maximum-likelihood shape ``k`` (early cut vs steady
  turnover vs fatigue decay) when enough stop events exist.
* Lindy conditional survival past fixed age milestones when enough concepts remain
  at risk inside the observed horizon.

Everything fails closed: keyword samples, active-only fetches, partially loaded
lists, and tiny cohorts return ``available: False`` with the exact reason.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

DEFAULT_WINDOW_DAYS = 90
COMPLETE_SHARE = 0.9
MIN_CONCEPTS = 10
MIN_EVENTS = 3
SMALL_SAMPLE_ENDED = 20
MIN_WEIBULL_EVENTS = 5
MIN_LINDY_AT_RISK = 5
MILESTONES = (7, 14, 30, 60, 90)
LINDY_AGES = (14, 30, 60)
LINDY_HORIZON = 30
_Z_95 = 1.959963984540054


def _clamp01(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def survival_at(steps: list[dict], day: int, max_observed: int) -> float | None:
    """Kaplan-Meier survival probability at ``day``, or None past ``max_observed``."""
    if day < 0 or day > max_observed:
        return None
    surv = 1.0
    for step in steps:
        if step["day"] > day:
            break
        surv = step["survival"]
    return surv


def rmst_at(steps: list[dict], tau: int) -> float:
    """Restricted mean survival time: exact area under the step curve on ``[0, tau]``."""
    if tau <= 0:
        return 0.0
    area, prev_t, prev_s = 0.0, 0, 1.0
    for step in steps:
        t = step["day"]
        if t >= tau:
            break
        area += prev_s * (t - prev_t)
        prev_t = t
        prev_s = step.get("_raw_survival", step["survival"])
    if tau > prev_t:
        area += prev_s * (tau - prev_t)
    return round(area, 1)


def kaplan_meier(observations: list[tuple[int, bool]]) -> dict:
    """Kaplan-Meier estimator for right-censored ``(duration_days, ended_event)`` pairs."""
    clean = [(max(1, int(days)), bool(ended)) for days, ended in observations]
    if not clean:
        return {"steps": [], "max_observed": 0, "median_days": None,
                "median_reached": False, "rmst_days": 0.0}

    max_observed = max(days for days, _ in clean)
    events_by_day: dict[int, int] = defaultdict(int)
    for days, ended in clean:
        if ended:
            events_by_day[days] += 1

    steps: list[dict] = []
    surv, greenwood_sum = 1.0, 0.0
    raw_pairs: list[tuple[int, float]] = []
    for day in sorted(events_by_day):
        d_i = events_by_day[day]
        n_i = sum(1 for t, _ in clean if t >= day)
        if n_i <= 0:
            continue
        surv *= (n_i - d_i) / n_i
        if surv <= 0.0:
            surv, se, ci_low, ci_high = 0.0, 0.0, 0.0, 0.0
        elif surv >= 1.0:
            surv, se, ci_low, ci_high = 1.0, 0.0, 1.0, 1.0
        else:
            if n_i > d_i:
                greenwood_sum += d_i / (n_i * (n_i - d_i))
            se = surv * math.sqrt(greenwood_sum)
            if se > 0.0:
                w = _Z_95 * se / (surv * abs(math.log(surv)))
                ci_low = _clamp01(surv ** math.exp(w))
                ci_high = _clamp01(surv ** math.exp(-w))
            else:
                ci_low = ci_high = surv
        raw_pairs.append((day, surv))
        steps.append({
            "day": day,
            "at_risk": n_i,
            "ended": d_i,
            "survival": round(surv, 4),
            "se": round(se, 4),
            "ci_low": round(ci_low, 4),
            "ci_high": round(ci_high, 4),
        })

    median_days: float | None = None
    for idx, (day, raw_s) in enumerate(raw_pairs):
        if raw_s <= 0.5 + 1e-12:
            if abs(raw_s - 0.5) <= 1e-12 and idx + 1 < len(raw_pairs):
                median_days = round((day + raw_pairs[idx + 1][0]) / 2.0, 1)
            else:
                median_days = float(day)
            break

    # Compute RMST using exact unrounded step heights
    area, prev_t, prev_s = 0.0, 0, 1.0
    for day, raw_s in raw_pairs:
        if day >= max_observed:
            break
        area += prev_s * (day - prev_t)
        prev_t, prev_s = day, raw_s
    if max_observed > prev_t:
        area += prev_s * (max_observed - prev_t)

    return {
        "steps": steps,
        "max_observed": max_observed,
        "median_days": median_days,
        "median_reached": median_days is not None,
        "rmst_days": round(area, 1),
    }


def weibull_mle(observations: list[tuple[int, bool]]) -> dict | None:
    """Right-censored Weibull MLE via profile score bisection on ``k``."""
    clean = [(max(1, int(days)), bool(ended)) for days, ended in observations]
    events = [days for days, ended in clean if ended]
    if len(events) < MIN_WEIBULL_EVENTS:
        return None
    t_max = max(days for days, _ in clean)
    if min(events) >= t_max:
        return None

    # Normalize by t_max so u_i in (0, 1] avoids overflow in u_i**k
    u_all = [days / t_max for days, _ in clean]
    ln_u_all = [math.log(u) for u in u_all]
    mean_ln_u_events = sum(math.log(days / t_max) for days in events) / len(events)

    def score(k: float) -> float:
        weights = [u ** k for u in u_all]
        denom = sum(weights)
        weighted_ln = sum(w * lu for w, lu in zip(weights, ln_u_all)) / denom
        return (1.0 / k) + mean_ln_u_events - weighted_ln

    lo, hi = 0.05, 20.0
    s_lo, s_hi = score(lo), score(hi)
    while s_lo <= 0.0 and lo > 0.005:
        lo *= 0.5
        s_lo = score(lo)
    while s_hi >= 0.0 and hi < 100.0:
        hi *= 2.0
        s_hi = score(hi)
    if s_lo <= 0.0 or s_hi >= 0.0:
        return None

    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if score(mid) > 0.0:
            lo = mid
        else:
            hi = mid
    k_hat = 0.5 * (lo + hi)
    sum_u_k = sum(u ** k_hat for u in u_all)
    scale_hat = t_max * ((sum_u_k / len(events)) ** (1.0 / k_hat))

    if k_hat < 0.85:
        regime = "early_cut"
    elif k_hat <= 1.15:
        regime = "steady_turnover"
    else:
        regime = "fatigue_decay"

    return {
        "shape_k": round(k_hat, 2),
        "scale_days": round(scale_hat, 1),
        "regime": regime,
    }


def lindy_conditional(steps: list[dict], observations: list[tuple[int, bool]], max_observed: int) -> list[dict] | None:
    """Conditional survival past milestone ages over ``LINDY_HORIZON`` more days."""
    rows = []
    for age in LINDY_AGES:
        horizon_end = age + LINDY_HORIZON
        if horizon_end > max_observed:
            continue
        at_risk = sum(1 for t, _ in observations if t > age)
        if at_risk < MIN_LINDY_AT_RISK:
            continue
        s_age = survival_at(steps, age, max_observed)
        s_next = survival_at(steps, horizon_end, max_observed)
        if s_age is None or s_next is None or s_age <= 0.0:
            continue
        rows.append({
            "after_days": age,
            "horizon_days": LINDY_HORIZON,
            "at_risk": at_risk,
            "still_active_share": round(_clamp01(s_next / s_age), 4),
        })
    return rows or None


def _parse_day(raw) -> date | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def analyze(concepts: list[dict], *, mode: str = "company", active_status: str = "all",
            loaded_share: float | None = None, window_days: int | None = DEFAULT_WINDOW_DAYS,
            as_of: date | None = None) -> dict:
    """Run cohort survival analysis across dated concepts when data quality gates pass."""
    as_of = as_of or date.today()
    base = {
        "available": False,
        "unit": "concept",
        "mode": mode,
        "active_status": active_status,
        "loaded_share": loaded_share,
        "window_days": window_days,
        "as_of": as_of.isoformat(),
    }
    if mode != "company":
        return {**base, "reason": "keyword_mode"}
    if active_status == "active":
        return {**base, "reason": "active_only"}
    if active_status != "all":
        return {**base, "reason": "inactive_only"}
    if loaded_share is None or loaded_share < COMPLETE_SHARE:
        return {**base, "reason": "partial_list"}

    cutoff = as_of - timedelta(days=window_days) if window_days is not None else None
    outside_window = excluded_undated = excluded_invalid = 0
    kept: list[tuple[dict, int, bool, str, str | None]] = []

    for concept in concepts:
        started_date = _parse_day(concept.get("started"))
        if started_date is None:
            excluded_undated += 1
            continue
        if started_date > as_of:
            excluded_invalid += 1
            continue
        if cutoff is not None and started_date < cutoff:
            outside_window += 1
            continue

        is_ended = (concept.get("status") == "inactive") or bool(concept.get("ended"))
        if is_ended:
            ended_date = _parse_day(concept.get("ended"))
            if ended_date is None:
                excluded_undated += 1
                continue
            if ended_date < started_date:
                excluded_invalid += 1
                continue
            if ended_date > as_of:
                is_ended = False
                duration_days = max(1, (as_of - started_date).days)
                ended_iso = None
            else:
                duration_days = max(1, (ended_date - started_date).days)
                ended_iso = ended_date.isoformat()
        else:
            duration_days = max(1, (as_of - started_date).days)
            ended_iso = None

        kept.append((concept, duration_days, is_ended, started_date.isoformat(), ended_iso))

    ended_count = sum(1 for _, _, is_ended, _, _ in kept if is_ended)
    active_count = len(kept) - ended_count
    counts = {
        "concepts_in_window": len(kept),
        "active_in_window": active_count,
        "ended_in_window": ended_count,
        "excluded_undated": excluded_undated,
        "excluded_invalid": excluded_invalid,
        "outside_window": outside_window,
    }
    if len(kept) < MIN_CONCEPTS:
        return {**base, "reason": "too_few_concepts", **counts}
    if ended_count < MIN_EVENTS:
        return {**base, "reason": "too_few_ended", **counts}

    observations = [(dur, is_ended) for _, dur, is_ended, _, _ in kept]
    km = kaplan_meier(observations)
    max_obs = km["max_observed"]
    tau = min(window_days, max_obs) if window_days is not None else max_obs
    milestones = {str(d): survival_at(km["steps"], d, max_obs) for d in MILESTONES}

    longest_active = [
        {"library_id": c.get("library_id"), "days": dur, "started": started_iso}
        for c, dur, is_ended, started_iso, _ in sorted(
            (row for row in kept if not row[2]),
            key=lambda row: (-row[1], str(row[0].get("library_id") or "")),
        )[:3]
    ]
    fastest_ended = [
        {"library_id": c.get("library_id"), "days": dur, "started": started_iso, "ended": ended_iso}
        for c, dur, is_ended, started_iso, ended_iso in sorted(
            (row for row in kept if row[2]),
            key=lambda row: (row[1], str(row[0].get("library_id") or "")),
        )[:3]
    ]

    return {
        **base,
        "available": True,
        **counts,
        "small_sample": ended_count < SMALL_SAMPLE_ENDED,
        "max_observed_days": max_obs,
        "tau_days": tau,
        "median_days": km["median_days"],
        "median_reached": km["median_reached"],
        "rmst_days": rmst_at(km["steps"], tau),
        "milestones": milestones,
        "curve": km["steps"],
        "weibull": weibull_mle(observations),
        "lindy": lindy_conditional(km["steps"], observations, max_obs),
        "longest_active": longest_active,
        "fastest_ended": fastest_ended,
    }


def format_summary(report: dict) -> list[str]:
    """Concise 5-10 line text block for ``testing.md`` (never for ``overview.md``)."""
    window_days = report.get("window_days")
    win_label = f"last {window_days} days" if window_days is not None else "all dated concepts"
    share = report.get("loaded_share")
    share_label = f"{round(share * 100)}%" if share is not None else "n/a"

    if not report.get("available"):
        reason = report.get("reason") or "unavailable"
        reasons = {
            "keyword_mode": "a keyword search loads a sample across advertisers, not one company list",
            "active_only": "only active ads were loaded, without ended ads",
            "inactive_only": "only ended ads were loaded, without active ads",
            "partial_list": (
                f"the list was read in part (loaded share {share_label})"
                if share is not None
                else "the total ad count was not reported by Meta (completeness unverified)"
            ),
            "too_few_concepts": (f"fewer than {MIN_CONCEPTS} dated concepts in the {win_label} window "
                                 f"({report.get('concepts_in_window', 0)} found)"),
            "too_few_ended": (f"fewer than {MIN_EVENTS} ended concepts with stop dates in the {win_label} window "
                              f"({report.get('ended_in_window', 0)} ended of {report.get('concepts_in_window', 0)})"),
        }
        detail = reasons.get(reason, str(reason))
        return [
            f"- Cohort duration: NOT MEASURABLE ({reason}). Reason: {detail}.",
            "- Do not state a median lifespan or cohort stop rate unless measured here or in the Survival table.",
        ]

    total = report["concepts_in_window"]
    active_n = report["active_in_window"]
    ended_n = report["ended_in_window"]
    excluded = report.get("excluded_undated", 0) + report.get("excluded_invalid", 0)
    tau = report.get("tau_days") or report["max_observed_days"]

    small_note = (
        f"; small sample (< {SMALL_SAMPLE_ENDED} ended concepts)"
        if report.get("small_sample", ended_n < SMALL_SAMPLE_ENDED)
        else ""
    )
    lines = [
        f"- Cohort window: {win_label}, unit = concept (active + ended), loaded share {share_label}; "
        f"{total} concepts ({active_n} still active, {ended_n} ended"
        + (f", {excluded} undated or invalid excluded" if excluded else "") + f"){small_note}.",
    ]
    if report.get("median_reached"):
        lines.append(
            f"- Median lifespan (Kaplan-Meier): {report['median_days']} days "
            f"(mean observed up to day {tau}: {report['rmst_days']} days)."
        )
    else:
        lines.append(
            f"- Median lifespan (Kaplan-Meier): not reached yet (more than half of concepts in this window are "
            f"still active; mean observed up to day {tau}: {report['rmst_days']} days)."
        )

    observed = [(d, val) for d, val in (report.get("milestones") or {}).items() if val is not None]
    if observed:
        lines.append("- Concepts still active by age: "
                     + ", ".join(f"{day}d {round(val * 100)}%" for day, val in observed) + ".")

    weibull = report.get("weibull")
    if weibull:
        regimes = {
            "early_cut": "most stopped ads end early while survivors hold longer",
            "steady_turnover": "steady stop rate across ages",
            "fatigue_decay": "stop rate rises with age (creative fatigue)",
        }
        lines.append(
            f"- Stop pattern (Weibull shape k = {weibull['shape_k']}, scale {weibull['scale_days']}d): "
            f"{regimes[weibull['regime']]}."
        )

    lindy = report.get("lindy")
    if lindy:
        parts = [f"past {row['after_days']}d ({row['at_risk']} at risk): "
                 f"{round(row['still_active_share'] * 100)}% still active {row['horizon_days']}d later"
                 for row in lindy]
        lines.append("- Conditional survival (Lindy): " + "; ".join(parts) + ".")

    longest = report.get("longest_active") or []
    fastest = report.get("fastest_ended") or []
    examples = []
    if longest:
        examples.append("longest active: " + ", ".join(f"id {r['library_id']} ({r['days']}d)" for r in longest))
    if fastest:
        examples.append("fastest ended: " + ", ".join(f"id {r['library_id']} ({r['days']}d)" for r in fastest))
    if examples:
        lines.append("- Examples: " + "; ".join(examples) + ".")

    lines.append("- Note: duration shows how long concepts stay on air before stopping, not profit or ROAS.")
    return lines
