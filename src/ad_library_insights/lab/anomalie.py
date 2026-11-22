"""Annunci fuori schema: deterministic selection of 2-4 cross-signal paradox ads.

Identifies concepts where independent observables pull in opposite directions (for
example: running long with tiny daily reach, breaking out fast in < 21 days, winning
reach with near-zero copy, investing many creatives with weak reach, or holding top rank
for 60+ days on a single creative) so specialists can focus reading on real anomalies at
negligible token cost.
"""
from __future__ import annotations

import math
import statistics

MIN_CONCEPTS = 5
MIN_REACH_PEER_CONCEPTS = 4
MAX_ANOMALIES = 4


def _quantile(sorted_vals: list[float], q: float) -> float:
    idx = min(len(sorted_vals) - 1, max(0, int(q * (len(sorted_vals) - 1))))
    return float(sorted_vals[idx])


def _is_active(ad: dict) -> bool:
    return ad.get("verdict") != "ended" and ad.get("status") != "inactive"


def select(ads: list[dict], *, mode: str = "company") -> dict:
    """Select up to ``MAX_ANOMALIES`` active concepts with strong cross-signal contradictions."""
    total_checked = len(ads)
    sample_scope = "company" if mode == "company" else "keyword_sample"
    if total_checked < MIN_CONCEPTS:
        return {
            "available": False,
            "reason": "too_few_concepts",
            "mode": mode,
            "sample_scope": sample_scope,
            "concepts_checked": total_checked,
            "status": "unavailable",
            "items": [],
        }

    active = [ad for ad in ads if _is_active(ad)]
    if len(active) < MIN_CONCEPTS:
        active = list(ads)

    days_vals = sorted(float(ad["days_running"]) for ad in active if ad.get("days_running") is not None)
    rpd_vals = sorted(float(ad["reach_per_day"]) for ad in active if ad.get("reach_per_day") is not None)
    body_vals = sorted(len((ad.get("body") or "").strip()) for ad in active)
    creatives_vals = sorted(int(ad.get("creatives") or 1) for ad in active)

    median_days = round(float(statistics.median(days_vals)), 1) if days_vals else 0.0
    p75_days = _quantile(days_vals, 0.75) if days_vals else 0.0
    has_reach_peers = len(rpd_vals) >= MIN_REACH_PEER_CONCEPTS
    median_rpd = round(float(statistics.median(rpd_vals)), 1) if has_reach_peers else None
    p25_rpd = _quantile(rpd_vals, 0.25) if has_reach_peers else None
    p75_rpd = _quantile(rpd_vals, 0.75) if has_reach_peers else None
    has_pos_reach_peers = has_reach_peers and median_rpd is not None and median_rpd > 0
    median_body_chars = round(float(statistics.median(body_vals)), 1) if body_vals else 0.0
    p75_creatives = _quantile(creatives_vals, 0.75) if creatives_vals else 1.0

    candidates: list[dict] = []
    for ad in active:
        lib_id = str(ad.get("library_id") or "")
        days = ad.get("days_running")
        rpd = ad.get("reach_per_day")
        body_text = (ad.get("body") or "").strip()
        body_chars = len(body_text)
        creatives = int(ad.get("creatives") or 1)
        imp_rank = ad.get("impression_rank")

        fired: list[tuple[str, float, list[str], str]] = []

        if (has_pos_reach_peers and days is not None and rpd is not None
                and days >= max(45, p75_days) and rpd <= min(median_rpd * 0.30, p25_rpd)):
            strength = (days / max(median_days, 1.0)) * (median_rpd / max(float(rpd), 1.0))
            detail = (
                f"{days}d on air vs {median_days}d median, yet only {int(round(rpd)):,}/day "
                f"vs {int(round(median_rpd)):,}/day median"
            )
            fired.append(("long_live_low_reach", round(strength, 2), ["reach", "copy"], detail))

        if (has_pos_reach_peers and days is not None and rpd is not None and rpd > 0
                and days <= 21 and rpd >= max(median_rpd * 2.5, p75_rpd * 1.5)):
            strength = float(rpd) / max(float(median_rpd), 1.0)
            detail = (
                f"only {days}d on air, already {int(round(rpd)):,}/day "
                f"vs {int(round(median_rpd)):,}/day median"
            )
            fired.append(("fast_breakout_reach", round(strength, 2), ["reach", "copy"], detail))

        if (has_pos_reach_peers and rpd is not None and rpd > 0
                and rpd >= max(median_rpd * 1.5, p75_rpd)
                and (body_chars == 0 or (body_chars <= 60 and median_body_chars >= 120))):
            strength = (float(rpd) / max(float(median_rpd), 1.0)) * (max(median_body_chars, 60.0) / max(float(body_chars), 10.0))
            detail = (
                f"{int(round(rpd)):,}/day reach vs {int(round(median_rpd)):,}/day median "
                f"with {body_chars} copy chars vs {int(round(median_body_chars))} median"
            )
            fired.append(("high_reach_minimal_copy", round(strength, 2), ["copy", "reach"], detail))

        if (has_pos_reach_peers and rpd is not None
                and creatives >= max(3, int(p75_creatives))
                and rpd <= min(median_rpd * 0.45, p25_rpd)):
            strength = float(creatives) * (float(median_rpd) / max(float(rpd), 1.0))
            detail = (
                f"{creatives} creatives built, yet only {int(round(rpd)):,}/day "
                f"vs {int(round(median_rpd)):,}/day median"
            )
            fired.append(("many_creatives_low_reach", round(strength, 2), ["reach", "copy"], detail))

        rank_top = imp_rank is not None and imp_rank <= max(3, len(active) // 5)
        reach_top = has_pos_reach_peers and rpd is not None and rpd > 0 and p75_rpd is not None and p75_rpd > 0 and rpd >= p75_rpd
        if days is not None and days >= max(60, p75_days) and creatives == 1 and (reach_top or (rpd is None and rank_top)):
            strength = float(days) / max(median_days, 1.0) + (2.0 if reach_top else 1.0)
            basis_txt = (
                f"{int(round(rpd)):,}/day reach" if reach_top
                else f"impression rank #{imp_rank}"
            )
            detail = f"{days}d active on just 1 creative with strong position ({basis_txt})"
            fired.append(("long_live_single_creative_top_rank", round(strength, 2), ["copy", "reach"], detail))

        if not fired:
            continue

        fired.sort(key=lambda row: (-row[1], row[0]))
        primary_kind, primary_strength, primary_lenses, primary_detail = fired[0]
        all_kinds = [row[0] for row in fired]
        all_lenses: list[str] = []
        for _, _, lenses, _ in fired:
            for ln in lenses:
                if ln not in all_lenses:
                    all_lenses.append(ln)

        opening = (body_text.splitlines() or [ad.get("headline") or ""])[0][:140]
        candidates.append({
            "library_id": lib_id,
            "advertiser": ad.get("advertiser"),
            "kind": primary_kind,
            "kinds": all_kinds,
            "lenses": all_lenses,
            "strength": primary_strength,
            "opening": opening,
            "detail": primary_detail,
            "metrics": {
                "days_running": days,
                "reach_per_day": rpd,
                "creatives": creatives,
                "body_chars": body_chars,
                "impression_rank": imp_rank,
                "media_type": ad.get("media_type"),
            },
        })

    # Prioritize distinct primary anomaly kinds first, then highest strength deterministically
    selected: list[dict] = []
    seen_ids: set[str] = set()
    seen_kinds: set[str] = set()
    ordered = sorted(candidates, key=lambda c: (-c["strength"], c["library_id"]))
    for cand in ordered:
        if len(selected) >= MAX_ANOMALIES:
            break
        if cand["kind"] not in seen_kinds and cand["library_id"] not in seen_ids:
            selected.append(cand)
            seen_kinds.add(cand["kind"])
            seen_ids.add(cand["library_id"])
    for cand in ordered:
        if len(selected) >= MAX_ANOMALIES:
            break
        if cand["library_id"] not in seen_ids:
            selected.append(cand)
            seen_ids.add(cand["library_id"])

    return {
        "available": True,
        "mode": mode,
        "sample_scope": sample_scope,
        "concepts_checked": total_checked,
        "active_checked": len(active),
        "status": "flagged" if selected else "none",
        "baselines": {
            "median_days": median_days,
            "median_reach_per_day": median_rpd,
            "median_body_chars": median_body_chars,
            "reach_peers": len(rpd_vals),
        },
        "items": selected,
    }


def format_summary(report: dict, *, lens: str | None = None) -> list[str]:
    """Concise deterministic summary strictly for ``reach.md`` and ``copy.md``."""
    scope_lbl = "keyword sample" if report.get("sample_scope") == "keyword_sample" else "company concepts"
    if not report.get("available"):
        return [
            f"- Out-of-pattern ads (Annunci fuori schema, {scope_lbl}): not available "
            f"({report.get('reason', 'too_few_concepts')}; {report.get('concepts_checked', 0)} checked).",
        ]

    items = report.get("items") or []
    if lens:
        lens_items = [row for row in items if lens in (row.get("lenses") or [])] or items
    else:
        lens_items = items

    if not lens_items:
        return [
            f"- Out-of-pattern ads (Annunci fuori schema, {report.get('concepts_checked', 0)} {scope_lbl}): "
            "no strong cross-signal contradiction flagged against this search's internal medians.",
        ]

    base = report.get("baselines") or {}
    rpd_base = f"{int(round(base['median_reach_per_day'])):,}/day reach, " if base.get("median_reach_per_day") is not None else ""
    lines = [
        f"- Selected {len(lens_items)} of {report.get('concepts_checked', 0)} {scope_lbl} with strong cross-signal "
        f"contradictions (baselines: {base.get('median_days', 0)}d on air, {rpd_base}{int(round(base.get('median_body_chars', 0)))} copy chars):",
    ]
    for row in lens_items[:MAX_ANOMALIES]:
        open_txt = f" — \"{row['opening'][:90]}\"" if row.get("opening") else ""
        lines.append(f"  - id {row['library_id']} [{row['kind']}]: {row['detail']}{open_txt}.")
    lines.append(
        "- Note: inspect whether these contradictions reflect retargeting/narrow budgets, visual hooks not shown in copy, "
        "or seasonal tests rather than assuming a winner or failure."
    )
    return lines
