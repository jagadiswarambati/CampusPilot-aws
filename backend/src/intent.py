"""Turns a natural-language request into structured parameters.

Amazon Bedrock is used only when USE_BEDROCK=true; otherwise (or on any failure) a
rule-based parser is used, so the app always works without paid services.
`minutes` is None when the user did not say how long they have: we ask, never guess.
"""
import json
import os
import re

DEFAULT_MODEL = "global.amazon.nova-2-lite-v1:0"
PROMPT = (
    "Extract a campus request as JSON with keys: minutes (int, minutes until next class, null if not stated), "
    "pages (int, pages to print, 0 if none), color (bool), food (bool), veg (bool, vegetarian only), "
    "meal (bool, true if they want a proper meal such as lunch, dinner or a thali, not just a snack), "
    "budget (number in rupees or null). Reply with JSON only."
)
MEAL_WORDS = r"\b(?:lunch|meal|thali|dinner|breakfast|biryani)\b"
FOOD_WORDS = (r"\b(?:lunch|food|meal|eat|eating|thali|snack|breakfast|dinner|hungry|canteen|"
              r"sandwich|wrap|coffee|biryani|kulche|chole)\b")


def _int(v, lo, hi, default=None):
    try:
        return max(lo, min(int(float(v)), hi))
    except (TypeError, ValueError, OverflowError):
        return default


def _flag(v):
    return v.strip().lower() in ("true", "yes", "1") if isinstance(v, str) else bool(v)


def _clean(d):
    budget = _int(d.get("budget"), 1, 100000)
    return {
        "minutes": _int(d.get("minutes"), 1, 240),
        "pages": _int(d.get("pages"), 0, 500, 0),
        "color": _flag(d.get("color")),
        "food": _flag(d.get("food")),
        "veg": _flag(d.get("veg")),
        "meal": _flag(d.get("meal")),
        "budget": float(budget) if budget else None,
    }


def _minutes(t):
    total = None
    m = re.search(r"(\d+)\s*(?:min|mins|minutes)\b", t)
    h = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", t)
    if m:
        total = int(m.group(1))
    if h:
        total = (total or 0) + round(float(h.group(1)) * 60)
    if re.search(r"\bhalf (?:an )?hour\b", t):
        total = (total or 0) + 30
    elif re.search(r"\b(?:an|one) hour\b", t):
        total = (total or 0) + 60
    return total


def parse_rules(text):
    t = text.lower()
    pages = re.search(r"(\d+)\s*(?:pages?|pgs?)\b", t)
    budget = (re.search(r"(?:₹\s*|\brs\.?\s*|\binr\s*|\bbudget(?:\s+(?:of|is))?\s*)(\d+)", t)
              or re.search(r"(\d+)\s*(?:rupees|rs\b|inr\b)", t))
    veg = bool(re.search(r"\bveg(?:etarian)?\b", t)) and not re.search(r"non[\s-]?veg", t)
    return _clean({
        "minutes": _minutes(t),
        "pages": pages and int(pages.group(1)),
        "color": re.search(r"colou?r", t),
        "food": veg or re.search(FOOD_WORDS, t),
        "veg": veg,
        "meal": re.search(MEAL_WORDS, t),
        "budget": budget and int(budget.group(1)),
    })


def parse_bedrock(text):
    import boto3  # lazy: the rule-based path has no AWS dependency
    from botocore.config import Config
    client = boto3.client("bedrock-runtime", config=Config(
        connect_timeout=3, read_timeout=8, retries={"max_attempts": 1}))  # must finish before Lambda's 15 s
    resp = client.converse(
        modelId=os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL),
        system=[{"text": PROMPT}],
        messages=[{"role": "user", "content": [{"text": text}]}],
        inferenceConfig={"maxTokens": 200, "temperature": 0},
    )
    out = resp["output"]["message"]["content"][0]["text"]
    return _clean(json.loads(out[out.index("{"): out.rindex("}") + 1]))


def parse_request(text):
    if os.environ.get("USE_BEDROCK") == "true":
        try:
            return {**parse_bedrock(text), "parser": "bedrock"}
        except Exception as exc:  # fall back, never fail the request
            print(f"Bedrock parse failed, using rules: {exc!r}")
    return {**parse_rules(text), "parser": "rules"}
