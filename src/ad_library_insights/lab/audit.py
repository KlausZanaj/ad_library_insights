"""Deterministic, non-blocking audit of generated Markdown reports against a data pack.

This module never calls an LLM and never blocks delivery: it returns structured
warnings so coordinators across any MCP client (Claude Code, Google Antigravity,
Codex CLI, Cursor) can fix mismatched IDs, stale/too-recent citations, drifted
``project.md`` unit-economics numbers, or ungrounded claims before replying.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_BARE_ID_RE = re.compile(r"(?<!\d)(\d{15,18})(?!\d)")
_CONTEXT_12_ID_RE = re.compile(r"(?:[?&]id=|\|\s*)(\d{12,18})(?=\s*\||[^\d]|$)")
_PREFIXED_ID_RE = re.compile(
    r"(?i)(?:(?<!per\s)(?<!test\s)\b(?:ad|annuncio)\s+#?|(?:\bad\s*id|\blibrary[\s_]+id|\bid)\s*#?:?\s*)(\d{4,18})\b"
)
_SLICE_ID_RE = re.compile(r"(?<!\d)(\d{12,18})(?!\d)|\bid\s+(\d{3,18})\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d[\d.,]*")
_CUT_LINE_RE = re.compile(r"(?i)(?:\bcut\s*(?:an\s+ad|rule|:)|\bregola\s+di\s+spegnimento\b|\bspegni\s+un\s+annuncio\b)")

_POSITIVE_RE = re.compile(
    r"(?i)\b(?:scaling|holding(?:\s+up)?|winner|vincente|tiene\s+bene|borrows\s+from|riprende\s+da|"
    r"top\s+ad|proven|consolidat[oa]|migliore|best[\s-]+performing)\b"
)
_RECENT_CAVEAT_RE = re.compile(
    r"(?i)(?:too\s+recent|troppo\s+recente|less\s+than\s+7|meno\s+di\s+7|<\s*7\s*(?:d|dd|gg|days|giorni)|"
    r"non\s+giudicabil|build\s+nothing|non\s+costruir)"
)
_REACH_CLAIM_RE = re.compile(
    r"(?i)\b\d[\d.,]*\s+(?:people|persone)\s+(?:per\s+day|al\s+giorno|reached|raggiunte)\b"
)
_REACH_NEGATION_RE = re.compile(
    r"(?i)(?:not\s+published|non\s+pubblicat[ao]|not\s+known|non\s+disponibil|no\s+reach|"
    r"nessuna\s+copertura|without\s+reach|senza\s+copertura|non\s+pubblica)"
)
_PROFIT_CLAIM_RE = re.compile(
    r"(?i)\b(?:competitor|advertiser|concorrente|inserzionista|this\s+ad|questo\s+annuncio)\b.{0,55}"
    r"(?:\b(?:is\s+profitable|makes\s+money|è\s+profittevole|guadagna)\b|"
    r"\b(?:spends?|spende|budget\s+(?:of|di))\s*[€$£]?\s*\d[\d.,]*|"
    r"\bhas\s+(?:a\s+)?roas\s+of\s*\d)"
)
_PROFIT_NEGATION_RE = re.compile(
    r"(?i)(?:not\s+proof|no\s+spend|does\s+not\s+publish|doesn't\s+publish|never\s+prove|"
    r"non\s+dimostra|non\s+pubblica|nessuna\s+spesa|non\s+è\s+prova|no\s+spend\s+or\s+sales|"
    r"senza\s+spesa|not\s+profitable)"
)
_SURVIVAL_CLAIM_RE = re.compile(
    r"(?i)\b(?:cut\s+rate|survival\s+rate|tasso\s+di\s+taglio|tasso\s+di\s+sopravvivenza)\b.{0,35}"
    r"\d+(?:[.,]\d+)?\s*%"
)
_SURVIVAL_NEGATION_RE = re.compile(
    r"(?i)(?:not\s+measurable|cannot\s+be\s+measured|non\s+misurabil|not\s+computed|"
    r"non\s+può\s+essere\s+misurat|non\s+disponibil)"
)

_PROJECT_LINE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("margin", re.compile(r"(?i)\b(?:net\s+margin\s+per\s+order|margin\s+per\s+order|margine\s+(?:netto\s+)?per\s+ordine)\b")),
    ("cpa", re.compile(r"(?i)\b(?:break-even\s+cpa|cpa\s+di\s+pareggio)\b")),
    ("roas", re.compile(r"(?i)\b(?:break-even\s+roas|roas\s+di\s+pareggio)\b")),
    ("round_total", re.compile(r"(?i)(?:budget,?\s*first\s+test\s+round|\bfirst\s+(?:test\s+)?round\b|\bprimo\s+giro\b|\bround\s*1\s*[:|])")),
)


def _parse_localized_number(token: str) -> float | None:
    """Parse Italian (``1.432,50`` / ``63,11``) and English (``1,432.50`` / ``63.11``) numbers."""
    clean = token.strip().strip(".,")
    if not clean:
        return None
    if "." in clean and "," in clean:
        if clean.rfind(",") > clean.rfind("."):
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(",", "")
    elif "." in clean:
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", clean):
            clean = clean.replace(".", "")
    elif "," in clean:
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", clean):
            clean = clean.replace(",", "")
        else:
            clean = clean.replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


def _extract_numbers(text: str) -> list[float]:
    values: list[float] = []
    for match in _NUMBER_RE.finditer(text):
        parsed = _parse_localized_number(match.group(0))
        if parsed is not None:
            values.append(parsed)
    return values


def _matches_expected(values: list[float], expected: float) -> bool:
    for val in values:
        if abs(val - expected) <= 0.06:
            return True
        if val.is_integer() and abs(expected) >= 100 and abs(val - expected) <= 1.05:
            return True
    return False


def _slice_known_ids(folder: Path) -> set[str]:
    found: set[str] = set()
    for name in ("overview.md", "copy.md", "creative.md", "reach.md", "testing.md"):
        path = folder / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in _SLICE_ID_RE.finditer(text):
            tok = m.group(1) or m.group(2)
            if tok:
                found.add(tok)
    return found


def _extract_cited_ids(text: str) -> set[str]:
    ids = {m.group(1) for m in _BARE_ID_RE.finditer(text)}
    for m in _CONTEXT_12_ID_RE.finditer(text):
        ids.add(m.group(1))
    for m in _PREFIXED_ID_RE.finditer(text):
        tok = m.group(1)
        if len(tok) == 4 and 1990 <= int(tok) <= 2100:
            continue
        ids.add(tok)
    return ids


def check_report(pack_folder: str | Path, report_text: str = "",
                 *, report_path: str | Path | None = None) -> dict:
    """Audit a Markdown report against ``pack_folder/manifest.json`` without blocking delivery."""
    folder = Path(pack_folder)
    manifest_path = folder / "manifest.json"
    if not folder.is_dir() or not manifest_path.is_file():
        raise ValueError(f"pack folder must exist and contain manifest.json: {folder}")

    text = report_text or ""
    if not text.strip() and report_path:
        rp = Path(report_path)
        if not rp.is_file():
            raise ValueError(f"report_path does not exist: {rp}")
        text = rp.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("report_text or report_path must provide non-empty Markdown")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = manifest.get("audit") or {}

    known_ids = {str(x) for x in (audit.get("ad_ids") or [])} | _slice_known_ids(folder)
    cited_ids = _extract_cited_ids(text)
    warnings: list[dict] = []
    checks_run: list[str] = ["unknown_ad_id", "forbidden_competitor_claim"]

    # 1. Unknown ad IDs (hallucinated or copied wrongly)
    if known_ids:
        for cid in sorted(cited_ids):
            if cid not in known_ids:
                warnings.append({
                    "code": "unknown_ad_id",
                    "severity": "warning",
                    "id": cid,
                    "message": f"Ad ID {cid} is not present in this pack's manifest or slices.",
                })

    # 2. Too-recent ads (<7 days) cited as winners/models without caveat
    too_recent_ids = {str(x) for x in (audit.get("too_recent_ids") or [])}
    if too_recent_ids:
        checks_run.append("too_recent_cited_as_winner")
        seen_recent: set[str] = set()
        for line in text.splitlines():
            for tid in too_recent_ids:
                if tid in seen_recent:
                    continue
                if re.search(rf"(?<!\d){re.escape(tid)}(?!\d)", line):
                    if _POSITIVE_RE.search(line) and not _RECENT_CAVEAT_RE.search(line):
                        seen_recent.add(tid)
                        warnings.append({
                            "code": "too_recent_cited_as_winner",
                            "severity": "warning",
                            "id": tid,
                            "message": f"Ad ID {tid} is marked too recent (<7d) but cited as winning/strong without caveat.",
                            "line": line.strip()[:180],
                        })

    # 3. Deterministic project.md math check (Level 3 / plan)
    proj_nums = audit.get("project_numbers") or {}
    if manifest.get("level") == "plan" and proj_nums:
        checks_run.append("project_number_mismatch")
        for line in text.splitlines():
            for key, pattern in _PROJECT_LINE_RULES:
                if key not in proj_nums:
                    continue
                if pattern.search(line):
                    nums = _extract_numbers(line)
                    if not nums:
                        continue
                    expected = float(proj_nums[key])
                    if not _matches_expected(nums, expected):
                        warnings.append({
                            "code": "project_number_mismatch",
                            "severity": "warning",
                            "field": key,
                            "expected": proj_nums[key],
                            "message": f"Line mentions {key} (expected {proj_nums[key]} from project.md) with different figures {nums}.",
                            "line": line.strip()[:180],
                        })
            if ("cut_low" in proj_nums or "cut_high" in proj_nums) and _CUT_LINE_RE.search(line):
                nums = _extract_numbers(line)
                if not nums:
                    continue
                low = proj_nums.get("cut_low")
                high = proj_nums.get("cut_high")
                per_ad = proj_nums.get("per_ad")
                # Ignore 2x/3x rule multipliers when real monetary thresholds sit well above 4
                monetary = [v for v in nums if v not in (2.0, 3.0)] if (low or 0) > 4.0 else nums
                if not monetary:
                    continue
                if low is not None and high is not None and len(monetary) >= 2:
                    for key, exp in (("cut_low", float(low)), ("cut_high", float(high))):
                        if not _matches_expected(monetary, exp):
                            warnings.append({
                                "code": "project_number_mismatch",
                                "severity": "warning",
                                "field": key,
                                "expected": proj_nums[key],
                                "message": f"Line mentions {key} (expected {proj_nums[key]} from project.md) with different figures {monetary}.",
                                "line": line.strip()[:180],
                            })
                else:
                    valid_single = [float(x) for x in (low, per_ad, high) if x is not None]
                    if not any(_matches_expected(monetary, exp) for exp in valid_single):
                        warnings.append({
                            "code": "project_number_mismatch",
                            "severity": "warning",
                            "field": "cut_rule",
                            "expected": f"{low}–{high}" if (low is not None and high is not None) else (low or high),
                            "message": f"Line mentions cut rule (expected {low} to {high} from project.md) with different figures {monetary}.",
                            "line": line.strip()[:180],
                        })

    # 4. Reach claimed when country has NO REACH IN
    if audit.get("has_reach") is False:
        checks_run.append("reach_claimed_without_data")
        for line in text.splitlines():
            if _REACH_CLAIM_RE.search(line) and not _REACH_NEGATION_RE.search(line):
                warnings.append({
                    "code": "reach_claimed_without_data",
                    "severity": "warning",
                    "message": "Report states people reached per day although this pack has no published reach in the searched country.",
                    "line": line.strip()[:180],
                })

    # 5. Competitor spend/profit claims & unmeasured survival rates
    for line in text.splitlines():
        if _PROFIT_CLAIM_RE.search(line) and not _PROFIT_NEGATION_RE.search(line):
            warnings.append({
                "code": "forbidden_competitor_claim",
                "severity": "warning",
                "message": "Report appears to assert competitor spend, profitability or ROAS (never published by Meta Ad Library).",
                "line": line.strip()[:180],
            })

    if audit.get("survival_measurable") is False:
        checks_run.append("unmeasured_survival_claim")
        for line in text.splitlines():
            if _SURVIVAL_CLAIM_RE.search(line) and not _SURVIVAL_NEGATION_RE.search(line):
                warnings.append({
                    "code": "unmeasured_survival_claim",
                    "severity": "warning",
                    "message": "Report states a percentage cut or survival rate even though survival is marked NOT MEASURABLE.",
                    "line": line.strip()[:180],
                })

    return {
        "ok": True,
        "status": "ok" if not warnings else "warnings",
        "blocking": False,
        "pack_folder": str(folder),
        "level": manifest.get("level"),
        "checks_run": checks_run,
        "checked_ad_ids": sorted(cited_ids),
        "warning_count": len(warnings),
        "warnings": warnings,
    }
