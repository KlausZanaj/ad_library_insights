"""Estimate how much an assistant will have to read for the Analysis and Plan levels.

The Data level is code only and uses no assistant at all. The other two hand the
collected data to the user's own assistant, so before starting the app shows what
will be sent and a rough size. It is an estimate on purpose: limits depend on the
assistant's plan and model and are not counted in credits, so no percentage is promised.

The numbers below are averages measured on real results; they are parameters, not rules.
"""
from __future__ import annotations

LEVELS = ("data", "analysis", "plan")
DEEP_CHOICES = (10, 20, 50)

TOKENS_PER_AD = 260            # one ad: copy, button, destination, dates, score, reach, audience
TOKENS_PER_IMAGE = 420         # one still frame or thumbnail read as a picture
FRAMES_PER_AD = 3              # start, middle, end
ADS_WITH_FRAMES = 10           # the creative review looks at the best ads only
BASE_TOKENS = {"analysis": 2500, "plan": 4500}       # instructions, signals, project card
PASSES = {"analysis": 3.0, "plan": 5.0}              # specialists re-read the same data
IMAGE_PASSES = {"analysis": 1.0, "plan": 2.0}
ANSWER_TOKENS = {"analysis": 3000, "plan": 7000}     # what the assistant writes back
BANDS = (("low", 30_000), ("medium", 90_000))        # above the last limit: "high"


def band(tokens: int) -> str:
    return next((name for name, limit in BANDS if tokens < limit), "high")


def estimate(level: str, ads: int, frames: bool = False) -> dict:
    """What a level sends to the assistant and roughly how much text that is."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}")
    ads = max(0, int(ads))
    if level == "data":
        return {"level": level, "uses_assistant": False, "ads": ads, "images": 0,
                "tokens": 0, "band": "none"}
    images = min(ads, ADS_WITH_FRAMES) * FRAMES_PER_AD if frames else 0
    tokens = round((BASE_TOKENS[level] + ads * TOKENS_PER_AD) * PASSES[level]
                   + images * TOKENS_PER_IMAGE * IMAGE_PASSES[level] + ANSWER_TOKENS[level])
    tokens = int(round(tokens, -2))
    return {"level": level, "uses_assistant": True, "ads": ads, "images": images,
            "tokens": tokens, "band": band(tokens), "passes": PASSES[level]}


def measure(text: str, images: int = 0, level: str = "analysis") -> dict:
    """Size of a prepared brief: its real length instead of the averages."""
    tokens = round(len(text) / 3.6 + images * TOKENS_PER_IMAGE)      # ~3.6 characters per token
    total = int(round(tokens * PASSES.get(level, 1.0) + ANSWER_TOKENS.get(level, 0), -2))
    return {"characters": len(text), "images": images, "tokens_single_pass": int(round(tokens, -2)),
            "tokens": total, "band": band(total)}
