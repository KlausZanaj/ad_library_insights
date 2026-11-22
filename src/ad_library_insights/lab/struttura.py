"""Su cosa si regge: concentration, NCD copy families, Shannon entropy, Pianka & JS drift.

All calculations use Python's standard library only (``math``, ``re``, ``zlib``) and
operate cleanly on both company searches and keyword samples with explicit scope labels:

* **Reach concentration:** share of read EU+UK reach held by the top 1, top 3 and
  top 20% concepts, HHI, effective number of winners (``1 / HHI``) and exact Gini.
* **Copy families (NCD ``zlib``):** clusters distinct textual angles using symmetric
  raw-DEFLATE Normalized Compression Distance (``wbits=-15``).
* **Shannon diversity:** effective categories and evenness across formats and landing
  domains.
* **Pianka niche overlap:** symmetric ``country × age_range × gender`` audience
  overlap between two advertisers when comparing two companies.
* **Jensen-Shannon audience drift:** shift in aggregate ``country × age × gender``
  reach distribution between saved snapshots of the same subject.
"""
from __future__ import annotations

import math
import re
import statistics
import zlib
from collections import Counter
from datetime import datetime, timezone

MIN_REACH_CONCEPTS = 3
MIN_TEXT_CHARS = 30
MIN_TEXT_CONCEPTS = 4
MAX_NCD_CONCEPTS = 60
NCD_THRESHOLD = 0.62
MIN_ENTROPY_ITEMS = 3

_URL_RE = re.compile(r"https?://\S+|\bwww\.\S+", re.I)
_WS_RE = re.compile(r"\s+")


def _finite_pos(val) -> float | None:
    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
        return None
    return float(val) if val > 0 else None


def _finite_nonneg(val) -> float | None:
    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
        return None
    return float(val) if val >= 0 else None


def reach_concentration(ads: list[dict], *, country: str | None = None) -> dict:
    """Measure how strongly read reach concentrates in the top concepts."""
    market_items: list[tuple[dict, float]] = []
    for ad in ads:
        val = _finite_nonneg(ad.get("reach_total"))
        if val is not None:
            market_items.append((ad, val))

    if len(market_items) >= MIN_REACH_CONCEPTS and sum(val for _, val in market_items) > 0:
        items = market_items
        scope = "market"
    elif len(market_items) < MIN_REACH_CONCEPTS and not any(ad.get("reach_in_market") for ad in ads):
        eu_uk_items: list[tuple[dict, float]] = []
        for ad in ads:
            r = ad.get("reach") or {}
            eu = _finite_pos(r.get("eu_total")) or 0.0
            uk = _finite_pos(r.get("uk_total")) or 0.0
            total = eu + uk
            if total > 0:
                eu_uk_items.append((ad, total))
        if len(eu_uk_items) >= MIN_REACH_CONCEPTS:
            items = eu_uk_items
            scope = "eu_uk"
        else:
            return {
                "measurable": False,
                "reason": "too_few_with_reach",
                "concepts_with_reach": len(eu_uk_items),
                "scope": None,
            }
    else:
        return {
            "measurable": False,
            "reason": "too_few_with_reach",
            "concepts_with_reach": len(market_items),
            "scope": "market" if market_items else None,
        }

    items.sort(key=lambda pair: (-pair[1], str(pair[0].get("library_id") or "")))
    n = len(items)
    total_reach = sum(val for _, val in items)
    shares = [val / total_reach for _, val in items]

    top1_share = round(shares[0], 3)
    top3_share = round(sum(shares[:3]), 3)
    top20_n = max(1, math.ceil(0.2 * n))
    top20pct_share = round(sum(shares[:top20_n]), 3)

    raw_hhi = sum(s * s for s in shares)
    hhi = round(raw_hhi, 4)
    effective_n = round(1.0 / raw_hhi, 1)
    norm_hhi = round(max(0.0, min(1.0, (raw_hhi - 1.0 / n) / (1.0 - 1.0 / n))), 3)

    asc = sorted(val for _, val in items)
    gini_raw = sum((2 * i - n - 1) * x_i for i, x_i in enumerate(asc, 1)) / (n * total_reach)
    gini = round(max(0.0, min(1.0, gini_raw)), 3)

    if top1_share >= 0.45 or (n >= 5 and top3_share >= 0.75) or norm_hhi >= 0.35:
        level = "concentrated"
    elif norm_hhi <= 0.12 and top1_share < 0.25:
        level = "balanced"
    else:
        level = "moderate"

    leaders = [
        {
            "library_id": ad.get("library_id"),
            "share": round(val / total_reach, 3),
            "reach": round(val),
            "cards_read": ad.get("reach_cards_read") or 1,
            "cards": ad.get("cards") or 1,
        }
        for ad, val in items[:3]
    ]

    return {
        "measurable": True,
        "scope": scope,
        "country": (country or "").upper() or None,
        "concepts_with_reach": n,
        "total_read_reach": round(total_reach),
        "top1_share": top1_share,
        "top3_share": top3_share,
        "top20pct_share": top20pct_share,
        "hhi": hhi,
        "normalized_hhi": norm_hhi,
        "effective_n": effective_n,
        "gini": gini,
        "level": level,
        "leaders": leaders,
    }


def _normalize_copy(text: str) -> str:
    cleaned = _URL_RE.sub(" ", text or "")
    return _WS_RE.sub(" ", cleaned.casefold()).strip()


def _deflate_len(data: bytes) -> int:
    """Raw DEFLATE length without zlib header/trailer overhead (``wbits=-15``)."""
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    return len(comp.compress(data) + comp.flush())


def _ncd(bx: bytes, by: bytes, cx: int, cy: int) -> float:
    cxy = min(_deflate_len(bx + b"\n" + by), _deflate_len(by + b"\n" + bx))
    denom = float(max(cx, cy, 1))
    val = (cxy - min(cx, cy)) / denom
    return max(0.0, min(1.0, val))


def copy_families(ads: list[dict]) -> dict:
    """Cluster concept texts into distinct copy families using raw-DEFLATE NCD."""
    kept: list[tuple[int, dict, bytes, int, str]] = []
    for idx, ad in enumerate(ads):
        raw = ad.get("body") or ""
        norm = _normalize_copy(raw)
        if len(norm) < MIN_TEXT_CHARS:
            continue
        payload = norm.encode("utf-8")
        first_line = (raw.strip().splitlines() or [""])[0][:140]
        kept.append((idx, ad, payload, _deflate_len(payload), first_line))

    total_with_text = len(kept)
    if total_with_text < MIN_TEXT_CONCEPTS:
        return {
            "measurable": False,
            "reason": "too_few_texts",
            "texts_evaluated": total_with_text,
            "total_with_text": total_with_text,
        }

    capped = total_with_text > MAX_NCD_CONCEPTS
    eval_items = kept[:MAX_NCD_CONCEPTS]

    families: list[dict] = []
    for rank_idx, ad, payload, clen, opening in eval_items:
        best_fam = None
        best_dist = NCD_THRESHOLD + 1.0
        for fam in families:
            dist = _ncd(payload, fam["bytes"], clen, fam["clen"])
            if dist <= NCD_THRESHOLD and dist < best_dist:
                best_dist = dist
                best_fam = fam
        lib_id = str(ad.get("library_id") or "")
        if best_fam is not None:
            best_fam["count"] += 1
            if lib_id:
                best_fam["member_ids"].append(lib_id)
        else:
            families.append({
                "rep_id": lib_id,
                "first_rank": rank_idx,
                "bytes": payload,
                "clen": clen,
                "opening": opening,
                "count": 1,
                "member_ids": [lib_id] if lib_id else [],
            })

    m = len(eval_items)
    k = len(families)
    diversity_ratio = round(k / float(m), 2)
    largest_size = max(f["count"] for f in families)
    largest_family_share = round(largest_size / float(m), 2)

    sample = eval_items[:25]
    pair_dists: list[float] = []
    for i in range(len(sample)):
        _, _, bi, ci, _ = sample[i]
        for j in range(i + 1, len(sample)):
            _, _, bj, cj, _ = sample[j]
            pair_dists.append(_ncd(bi, bj, ci, cj))
    median_ncd = round(float(statistics.median(pair_dists)), 3) if pair_dists else 0.0

    ordered_fams = sorted(families, key=lambda f: (-f["count"], f["first_rank"]))
    top_families = [
        {
            "representative_id": f["rep_id"],
            "size": f["count"],
            "share": round(f["count"] / float(m), 2),
            "opening": f["opening"],
            "member_ids": f["member_ids"][:5],
        }
        for f in ordered_fams[:4]
    ]

    return {
        "measurable": True,
        "evaluated": m,
        "total_with_text": total_with_text,
        "capped": capped,
        "threshold": NCD_THRESHOLD,
        "families_count": k,
        "diversity_ratio": diversity_ratio,
        "largest_family_share": largest_family_share,
        "median_pairwise_ncd": median_ncd,
        "top_families": top_families,
    }


def _entropy_stats(counter: Counter[str]) -> dict:
    total = sum(counter.values())
    k = len(counter)
    if total < MIN_ENTROPY_ITEMS:
        return {"measurable": False, "items": total, "categories": k}
    h = 0.0
    for count in counter.values():
        if count > 0:
            p = count / float(total)
            h -= p * math.log2(p)
    h = max(0.0, h)
    effective_k = round(2.0 ** h, 2)
    evenness = round(h / math.log2(k), 3) if k > 1 else 0.0
    dom, dom_count = counter.most_common(1)[0]
    dom_share = round(dom_count / float(total), 3)
    if dom_share >= 0.80 or k == 1:
        label = "concentrated"
    elif k >= 2 and evenness >= 0.75:
        label = "balanced"
    else:
        label = "skewed"
    return {
        "measurable": True,
        "items": total,
        "categories": k,
        "entropy_bits": round(h, 3),
        "effective_k": effective_k,
        "evenness": evenness,
        "dominant": dom,
        "dominant_share": dom_share,
        "label": label,
    }


def shannon_diversity(ads: list[dict]) -> dict:
    """Compute Shannon entropy, effective count and evenness on formats and destinations."""
    fmt_counts: Counter[str] = Counter()
    dest_counts: Counter[str] = Counter()
    for ad in ads:
        fmt = (ad.get("media_type") or "").strip().casefold()
        if fmt and fmt != "unknown":
            fmt_counts[fmt] += 1
        dom = (ad.get("landing_domain") or "").strip().casefold()
        if dom:
            dest_counts[dom] += 1
    return {
        "formats": _entropy_stats(fmt_counts),
        "destinations": _entropy_stats(dest_counts),
    }


def _breakdown_shares(result: dict) -> tuple[dict[tuple[str, str, str], float], int, int]:
    counts: Counter[tuple[str, str, str]] = Counter()
    ads_count = 0
    for ad in result.get("ads") or []:
        cells = (ad.get("reach") or {}).get("breakdown_3d") or []
        has_pos = False
        for cell in cells:
            c = str(cell.get("country") or "")
            a = str(cell.get("age_range") or "?")
            for g in ("male", "female", "unknown"):
                val = int(cell.get(g) or 0)
                if val > 0:
                    counts[(c, a, g)] += val
                    has_pos = True
        if has_pos:
            ads_count += 1
    if ads_count == 0 and (result.get("audience_distribution") or {}).get("cells"):
        dist = result["audience_distribution"]
        for cell in dist["cells"]:
            val = float(cell.get("reach") or cell.get("share") or 0.0)
            if val > 0:
                counts[(str(cell.get("country") or ""), str(cell.get("age_range") or "?"), str(cell.get("gender") or "?"))] += val
        ads_count = int(dist.get("ads_with_breakdown") or (1 if counts else 0))

    total = sum(counts.values())
    if not total or ads_count == 0:
        return {}, 0, 0
    return ({k: v / float(total) for k, v in counts.items()}, ads_count, round(total))


def pianka_overlap(first: dict, second: dict) -> dict:
    """Symmetric Pianka audience niche overlap over 3D ``country × age_range × gender`` cells."""
    p, ads_a, tot_a = _breakdown_shares(first)
    q, ads_b, tot_b = _breakdown_shares(second)
    if ads_a == 0 or ads_b == 0 or not p or not q:
        return {"measurable": False, "reason": "no_breakdown_3d", "ads_a": ads_a, "ads_b": ads_b}

    shared_keys = set(p) & set(q)
    dot = sum(p[k] * q[k] for k in shared_keys)
    norm_a = sum(v * v for v in p.values())
    norm_b = sum(v * v for v in q.values())
    denom = math.sqrt(norm_a * norm_b)
    overlap = max(0.0, min(1.0, dot / denom)) if denom > 0 else 0.0
    overlap_r = round(overlap, 3)

    band = "high" if overlap_r >= 0.80 else ("moderate" if overlap_r >= 0.50 else "low")

    shared_ranked = sorted(
        (k for k in shared_keys if min(p[k], q[k]) > 0),
        key=lambda k: (-min(p[k], q[k]), k),
    )
    shared_segments = [
        {"country": c, "age_range": a, "gender": g,
         "share_a": round(p[(c, a, g)], 3), "share_b": round(q[(c, a, g)], 3)}
        for c, a, g in shared_ranked[:3]
    ]

    all_keys = sorted(set(p) | set(q))
    distinct_a_keys = sorted(
        (k for k in all_keys if p.get(k, 0.0) - q.get(k, 0.0) >= 0.05),
        key=lambda k: (-(p.get(k, 0.0) - q.get(k, 0.0)), k),
    )
    distinct_b_keys = sorted(
        (k for k in all_keys if q.get(k, 0.0) - p.get(k, 0.0) >= 0.05),
        key=lambda k: (-(q.get(k, 0.0) - p.get(k, 0.0)), k),
    )
    distinct_a = [
        {"country": c, "age_range": a, "gender": g,
         "share_a": round(p.get((c, a, g), 0.0), 3), "share_b": round(q.get((c, a, g), 0.0), 3),
         "gap": round(p.get((c, a, g), 0.0) - q.get((c, a, g), 0.0), 3)}
        for c, a, g in distinct_a_keys[:3]
    ]
    distinct_b = [
        {"country": c, "age_range": a, "gender": g,
         "share_a": round(p.get((c, a, g), 0.0), 3), "share_b": round(q.get((c, a, g), 0.0), 3),
         "gap": round(q.get((c, a, g), 0.0) - p.get((c, a, g), 0.0), 3)}
        for c, a, g in distinct_b_keys[:3]
    ]

    return {
        "measurable": True,
        "overlap": overlap_r,
        "band": band,
        "ads_a": ads_a,
        "ads_b": ads_b,
        "total_reach_a": tot_a,
        "total_reach_b": tot_b,
        "shared_segments": shared_segments,
        "distinct_a": distinct_a,
        "distinct_b": distinct_b,
    }


def _cells_to_dist(snap: dict) -> dict[tuple[str, str, str], float]:
    cells = ((snap.get("audience_distribution") or {}).get("cells")) or []
    raw: dict[tuple[str, str, str], float] = {}
    for cell in cells:
        val = float(cell.get("share") or cell.get("reach") or 0.0)
        if val > 0:
            key = (str(cell.get("country") or ""), str(cell.get("age_range") or "?"), str(cell.get("gender") or "?"))
            raw[key] = raw.get(key, 0.0) + val
    tot = sum(raw.values())
    return {k: v / tot for k, v in raw.items()} if tot > 0 else {}


def _parse_iso_utc(raw) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def audience_js_drift(snapshots: list[dict]) -> dict:
    """Measure Jensen-Shannon audience shift between saved snapshots with breakdown cells."""
    valid = sorted(
        (s for s in (snapshots or []) if _cells_to_dist(s)),
        key=lambda s: (
            _parse_iso_utc(s.get("taken_at")) or datetime.min.replace(tzinfo=timezone.utc),
            str(s.get("taken_at") or ""),
        ),
    )
    if len(valid) < 2:
        return {
            "measurable": False,
            "reason": "too_few_snapshots_with_audience",
            "snapshots_with_audience": len(valid),
        }

    before, after = valid[0], valid[-1]
    p = _cells_to_dist(before)
    q = _cells_to_dist(after)
    all_keys = sorted(set(p) | set(q))

    jsd = 0.0
    for k in all_keys:
        pk = p.get(k, 0.0)
        qk = q.get(k, 0.0)
        mk = 0.5 * (pk + qk)
        if pk > 0.0 and mk > 0.0:
            jsd += 0.5 * pk * math.log2(pk / mk)
        if qk > 0.0 and mk > 0.0:
            jsd += 0.5 * qk * math.log2(qk / mk)
    jsd = max(0.0, min(1.0, jsd))
    js_distance = round(math.sqrt(jsd), 3)
    js_divergence = round(jsd, 4)

    state = "shifted" if js_distance >= 0.30 else ("drifting" if js_distance >= 0.15 else "stable")

    gainer_keys = sorted(
        (k for k in all_keys if q.get(k, 0.0) - p.get(k, 0.0) >= 0.03),
        key=lambda k: (-(q.get(k, 0.0) - p.get(k, 0.0)), k),
    )
    loser_keys = sorted(
        (k for k in all_keys if p.get(k, 0.0) - q.get(k, 0.0) >= 0.03),
        key=lambda k: (-(p.get(k, 0.0) - q.get(k, 0.0)), k),
    )
    top_gainers = [
        {"country": c, "age_range": a, "gender": g,
         "before": round(p.get((c, a, g), 0.0), 3), "after": round(q.get((c, a, g), 0.0), 3),
         "delta": round(q.get((c, a, g), 0.0) - p.get((c, a, g), 0.0), 3)}
        for c, a, g in gainer_keys[:3]
    ]
    top_losers = [
        {"country": c, "age_range": a, "gender": g,
         "before": round(p.get((c, a, g), 0.0), 3), "after": round(q.get((c, a, g), 0.0), 3),
         "delta": round(q.get((c, a, g), 0.0) - p.get((c, a, g), 0.0), 3)}
        for c, a, g in loser_keys[:3]
    ]

    dt1 = _parse_iso_utc(before.get("taken_at"))
    dt2 = _parse_iso_utc(after.get("taken_at"))
    days_between = round(max(0.0, (dt2 - dt1).total_seconds() / 86400.0), 1) if dt1 and dt2 else 0.0

    return {
        "measurable": True,
        "js_distance": js_distance,
        "js_divergence": js_divergence,
        "state": state,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "from_taken_at": before.get("taken_at"),
        "to_taken_at": after.get("taken_at"),
        "days_between": days_between,
        "ads_before": (before.get("audience_distribution") or {}).get("ads_with_breakdown"),
        "ads_after": (after.get("audience_distribution") or {}).get("ads_with_breakdown"),
        "snapshots_with_audience": len(valid),
    }


def analyze(ads: list[dict], signals: dict | None = None, *, mode: str = "company",
            country: str | None = None, snapshots: list[dict] | None = None) -> dict:
    """Compute structural concentration, copy families, Shannon mix and optional JS drift."""
    rc = reach_concentration(ads, country=country)
    cf = copy_families(ads)
    sh = shannon_diversity(ads)
    js = audience_js_drift(snapshots or [])
    available = any((
        rc.get("measurable"),
        cf.get("measurable"),
        sh["formats"].get("measurable"),
        sh["destinations"].get("measurable"),
        js.get("measurable"),
    ))
    return {
        "available": available,
        "mode": mode,
        "sample_scope": "company" if mode == "company" else "keyword_sample",
        "country": (country or "").upper() or None,
        "concepts_total": len(ads),
        "reach_concentration": rc,
        "copy_families": cf,
        "shannon": sh,
        "audience_drift": js,
    }


def format_reach_summary(report: dict) -> list[str]:
    """Concise structural block strictly for ``reach.md`` (never ``overview.md`` or ``copy.md``)."""
    scope_lbl = "keyword sample across advertisers" if report.get("sample_scope") == "keyword_sample" else "advertiser concepts loaded"
    rc = report.get("reach_concentration") or {}
    lines: list[str] = []
    if rc.get("measurable"):
        n = rc["concepts_with_reach"]
        scope_kind = "searched country reach" if rc.get("scope") == "market" else "EU+UK total reach"
        leaders = ", ".join(
            f"id {row['library_id']} ({round(row['share'] * 100)}%)"
            for row in (rc.get("leaders") or [])[:3]
        )
        lines.append(
            f"- Reach concentration ({scope_lbl}; {n} concepts with {scope_kind}): "
            f"{rc['level']} — top 1 holds {round(rc['top1_share'] * 100)}%, top 3 hold {round(rc['top3_share'] * 100)}% "
            f"(HHI {rc['hhi']}, normalized {rc['normalized_hhi']}, effective concepts {rc['effective_n']}, Gini {rc['gini']})."
        )
        if leaders:
            lines.append(f"- Top reach leaders among those {n} read concepts: {leaders}.")
    else:
        lines.append(
            f"- Reach concentration ({scope_lbl}): not available ({rc.get('reason', 'too_few_with_reach')}; "
            f"{rc.get('concepts_with_reach', 0)} concepts carried published reach)."
        )

    sh = report.get("shannon") or {}
    dest = sh.get("destinations") or {}
    fmt = sh.get("formats") or {}
    ent_parts = []
    if dest.get("measurable"):
        ent_parts.append(
            f"destinations {dest['label']} ({dest['categories']} domains, effective {dest['effective_k']}, "
            f"evenness {dest['evenness']}, top {dest['dominant']} at {round(dest['dominant_share'] * 100)}%)"
        )
    if fmt.get("measurable"):
        ent_parts.append(
            f"formats {fmt['label']} ({fmt['categories']} types, effective {fmt['effective_k']}, "
            f"evenness {fmt['evenness']}, top {fmt['dominant']} at {round(fmt['dominant_share'] * 100)}%)"
        )
    if ent_parts:
        lines.append("- Structural Shannon diversity: " + "; ".join(ent_parts) + ".")

    js = report.get("audience_drift") or {}
    if js.get("measurable"):
        gains = ", ".join(f"{g['country']}/{g['age_range']}/{g['gender']} ({round(g['delta'] * 100):+}pp)" for g in js.get("top_gainers") or [])
        lines.append(
            f"- Audience drift across snapshots (JS distance {js['js_distance']}, {js['state']} over "
            f"{js['days_between']}d across {js['snapshots_with_audience']} snapshots)"
            + (f"; gainers: {gains}" if gains else "") + "."
        )

    lines.append(
        "- Note: concentration shares apply strictly to the concepts whose reach was read (one person may see several concepts); "
        "concentrated delivery can reflect one runaway concept or intentional budget consolidation rather than weakness."
    )
    return lines


def format_copy_summary(report: dict) -> list[str]:
    """Concise copy-family block strictly for ``copy.md`` (never ``overview.md`` or ``reach.md``)."""
    scope_lbl = "keyword sample across advertisers" if report.get("sample_scope") == "keyword_sample" else "advertiser concepts loaded"
    cf = report.get("copy_families") or {}
    lines: list[str] = []
    if cf.get("measurable"):
        cap_note = f" (capped at top {MAX_NCD_CONCEPTS} of {cf['total_with_text']})" if cf.get("capped") else ""
        lines.append(
            f"- Copy families (NCD zlib across {cf['evaluated']} concepts with body text >= {MIN_TEXT_CHARS} chars{cap_note}, "
            f"{scope_lbl}): {cf['families_count']} distinct families (diversity ratio {cf['diversity_ratio']}, "
            f"largest family {round(cf['largest_family_share'] * 100)}% of evaluated texts, median pairwise NCD {cf['median_pairwise_ncd']})."
        )
        top_desc = "; ".join(
            f"rep id {row['representative_id']} ({row['size']} texts, {round(row['share'] * 100)}%: \"{row['opening']}\")"
            for row in (cf.get("top_families") or [])[:3]
        )
        if top_desc:
            lines.append(f"- Largest text clusters: {top_desc}.")
    else:
        lines.append(
            f"- Copy families (NCD zlib, {scope_lbl}): not available ({cf.get('reason', 'too_few_texts')}; "
            f"{cf.get('texts_evaluated', 0)} concepts had >= {MIN_TEXT_CHARS} chars)."
        )

    fmt = ((report.get("shannon") or {}).get("formats")) or {}
    if fmt.get("measurable"):
        lines.append(
            f"- Format entropy: {fmt['label']} ({fmt['categories']} formats, effective {fmt['effective_k']}, "
            f"evenness {fmt['evenness']})."
        )

    lines.append(
        "- Note: compression-based clustering groups similar wording rather than semantic persuasion quality; "
        "one repeated template can reflect systematic hook/CTA iteration or copy reuse across placements."
    )
    return lines
