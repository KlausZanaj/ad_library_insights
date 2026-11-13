"""Break ad copy into hook, promise, proof and call to action.

Rule-based and deterministic (no model call): position in the text, punctuation,
digits and symbols carry most of the signal and work in any language; a small
multilingual phrase list (``data/lexicon.json``) refines the labels. The output is
a starting structure for a human or an LLM to refine, not a semantic judgement.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from functools import lru_cache
from importlib import resources

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_LEADING_DECORATION = re.compile(r"^[^\w¿¡\"'(\[]+", re.UNICODE)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿]")
_POINTER = re.compile("[\U0001F449\U0001F447➡⬇\U0001F517]")
_URL = re.compile(r"https?://\S+|\bwww\.\S+", re.IGNORECASE)
_CURRENCY = re.compile(r"[€$£]\s?\d|\d\s?(?:[€$£]|eur\b|usd\b|gbp\b)", re.IGNORECASE)
_PERCENT = re.compile(r"\d\s?%")
_STATISTIC = re.compile(r"\d[\d.,]*\s?(?:%|\+|/\s?5\b|x\b)|[★⭐]|\b\d{1,3}(?:[.,]\d{3})+\b")
_HASHTAG = re.compile(r"#\w+")
_LIST_LINE = re.compile(r"^\s*(?:[-•✓✔✅]|\d️?⃣|\d+[.)])")

CTA_KINDS = {
    "purchase": ("shop now", "buy now", "order now", "get offer", "buy tickets", "see menu"),
    "lead": ("sign up", "get quote", "apply now", "subscribe", "book now", "contact us",
             "download", "request time", "install now", "use app"),
    "message": ("send message", "send whatsapp message", "call now", "message page"),
    "learn": ("learn more", "see details", "see more", "watch more", "open link",
              "visit instagram profile", "get directions"),
}


@lru_cache(maxsize=1)
def _patterns() -> dict[str, re.Pattern]:
    raw = json.loads(resources.files(__package__).joinpath("data/lexicon.json")
                     .read_text(encoding="utf-8"))
    return {
        name: re.compile(r"(?<!\w)(?:" + "|".join(sorted(map(re.escape, phrases), key=len, reverse=True))
                         + r")(?!\w)", re.IGNORECASE)
        for name, phrases in raw.items() if isinstance(phrases, list)
    }


def split_segments(body: str) -> list[str]:
    """Lines, then sentences within each line."""
    segments = []
    for line in (body or "").splitlines():
        segments.extend(part.strip() for part in _SENTENCE_END.split(line.strip()) if part.strip())
    return segments


def _has(name: str, text: str) -> bool:
    return bool(_patterns()[name].search(text))


def hook_type(text: str) -> str:
    """Classify an opening line. First matching rule wins."""
    bare = _LEADING_DECORATION.sub("", text)
    if "?" in text:
        return "question"
    if _PERCENT.search(text) or _CURRENCY.search(text) or _has("offer", text):
        return "offer"
    if _has("pain", text):
        return "pain_point"
    if _has("proof_review", text):
        return "social_proof"
    if re.search(r"\d", text):
        return "number"
    if _patterns()["cta_verbs"].match(bare) or _patterns()["benefit"].match(bare):
        return "command"
    return "statement"


def proof_kinds(text: str) -> list[str]:
    kinds = []
    is_discount = bool(_PERCENT.search(text)) and _has("offer", text)
    if _STATISTIC.search(text) and not is_discount and not _CURRENCY.search(text):
        kinds.append("statistic")
    if _has("proof_review", text):
        kinds.append("reviews")
    if _has("proof_guarantee", text):
        kinds.append("guarantee")
    if _has("proof_authority", text):
        kinds.append("authority")
    return kinds


def cta_kind(button: str | None) -> str | None:
    if not button:
        return None
    label = button.casefold()
    return next((kind for kind, labels in CTA_KINDS.items() if label in labels), "other")


def analyze_ad(ad: dict) -> dict:
    """Structured copy breakdown of one ad record."""
    body = ad.get("body") or ""
    segments = split_segments(body)
    used: set[int] = set()

    hook = None
    if segments:
        used.add(0)
        hook = {"text": segments[0], "type": hook_type(segments[0])}

    # the closing line is the last sentence, looking past a trailing row of hashtags
    closing = None
    last = len(segments) - 1
    while last > 0 and not _HASHTAG.sub("", segments[last]).strip():
        last -= 1
    if last > 0:
        text = segments[last]
        if _has("cta_verbs", text) or _POINTER.search(text) or _URL.search(text):
            closing = text
            used.add(last)

    proof = []
    for index, text in enumerate(segments):
        kinds = proof_kinds(text)
        if kinds and (index == 0 or index not in used):  # a hook can carry proof too
            proof.append({"text": text, "kinds": kinds})
            used.add(index)

    remaining = [(i, s) for i, s in enumerate(segments) if i not in used]
    promise = next((s for _, s in remaining if _has("benefit", s)),
                   remaining[0][1] if remaining else None)

    button = ad.get("cta")
    structure = [part for part, present in (
        (f"hook:{hook['type']}" if hook else "", hook),
        ("promise", promise), ("proof", proof), ("cta", closing or button)) if present]

    return {
        "library_id": ad.get("library_id"),
        "advertiser": ad.get("advertiser"),
        "hook": hook,
        "promise": {"text": promise} if promise else None,
        "proof": proof,
        "cta": {
            "button": button,
            "kind": cta_kind(button),
            "closing_line": closing,
            "urgency": any(_has("urgency", s) for s in segments[-3:]),
        },
        "headline": ad.get("headline"),
        "format": {
            "characters": len(body),
            "lines": len(body.splitlines()),
            "emoji": len(_EMOJI.findall(body)),
            "hashtags": len(_HASHTAG.findall(body)),
            "has_list": sum(bool(_LIST_LINE.match(line)) for line in body.splitlines()) >= 2,
            "mentions_price": bool(_CURRENCY.search(body + " " + (ad.get("description") or ""))),
            "mentions_offer": bool(_PERCENT.search(body)) or _has("offer", body),
        },
        "structure": " > ".join(structure),
    }


def _share(count: int, total: int) -> float:
    return round(count / total, 2) if total else 0.0


def summarize(analyses: list[dict]) -> dict:
    """Recurring patterns across a set of breakdowns (typically the top-ranked ads)."""
    total = len(analyses)
    with_copy = [a for a in analyses if a["hook"]]
    lengths = [a["format"]["characters"] for a in with_copy]
    proof_counter = Counter(kind for a in analyses for item in a["proof"] for kind in item["kinds"])
    return {
        "ads_analyzed": total,
        "hook_types": dict(Counter(a["hook"]["type"] for a in with_copy).most_common()),
        "share_with_proof": _share(sum(bool(a["proof"]) for a in analyses), total),
        "proof_kinds": dict(proof_counter.most_common()),
        "cta_buttons": dict(Counter(a["cta"]["button"].title() for a in analyses
                                    if a["cta"]["button"]).most_common()),
        "cta_kinds": dict(Counter(a["cta"]["kind"] for a in analyses if a["cta"]["kind"]).most_common()),
        "share_with_closing_line": _share(sum(bool(a["cta"]["closing_line"]) for a in analyses), total),
        "share_with_urgency": _share(sum(a["cta"]["urgency"] for a in analyses), total),
        "share_with_emoji": _share(sum(a["format"]["emoji"] > 0 for a in analyses), total),
        "share_mentioning_price": _share(sum(a["format"]["mentions_price"] for a in analyses), total),
        "share_mentioning_offer": _share(sum(a["format"]["mentions_offer"] for a in analyses), total),
        "median_characters": int(statistics.median(lengths)) if lengths else 0,
        "common_structures": dict(Counter(a["structure"] for a in with_copy).most_common(3)),
    }
