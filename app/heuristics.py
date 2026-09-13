"""
Cheap regex heuristics that flag willingness-to-pay proxies in a raw signal.
No LLM. These are deliberately high-recall / medium-precision: the LLM stage
(TODO) will refine them. Weights below are placeholders — tune together.

Each flag answers a different validation question:
  mentions_existing_tool   -> budget already exists in this category (they pay someone today)
  mentions_diy_workaround  -> pain strong enough to build a hack (spreadsheet/script/VA)
  asks_for_recommendation  -> explicit demand for a solution ("is there a tool that...")
  mentions_cost_or_time    -> quantified pain ($, hours/week) = easier to price
  expresses_frustration    -> emotional intensity (weakest signal alone, strong combined)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

_FLAGS = {
    "mentions_existing_tool": re.compile(
        r"\b(we|i)\s+(currently\s+)?(use|used|using|pay(ing)?\s+for|switched\s+(from|to)|tried|trialed|subscribe\w*\s+to)\s+"
        r"(a\s+|an\s+|the\s+)?[A-Z][\w.]+|"
        r"\b(quickbooks|xero|hubspot|salesforce|notion|airtable|zapier|monday\.com|asana|trello|jobber|housecall|servicetitan|"
        r"dentrix|eaglesoft|opendental|simplepractice|jane\s?app|cliniko|mindbody|appfolio|buildium|yardi|toast|square|shopify|"
        r"freshbooks|wave|gusto|stripe|mailchimp|klaviyo|calendly|acuity|typeform|clickup|pipedrive|zoho)\b",
        re.I,
    ),
    "mentions_diy_workaround": re.compile(
        r"\b(spreadsheet|excel|google\s+sheets?|built\s+(my|our)\s+own|wrote\s+a\s+script|hacked\s+together|"
        r"manually|by\s+hand|copy[\s-]*past\w+|virtual\s+assistant|\bVA\b|hired\s+someone\s+to|"
        r"workaround|duct[\s-]*tape|zapier\s+hack|macro)\b",
        re.I,
    ),
    "asks_for_recommendation": re.compile(
        r"\b(is\s+there\s+(a|an|any|some|something)\s+(\w+\s+){0,2}(tool|app|software|service|platform|way|thing|alternative)|"
        r"(anyone|anybody|does\s+anyone|do\s+you|you\s+guys)\s+(know|use|recommend|have|found|tried)\s+(of\s+)?(a|an|any|some)?\s*(\w+\s+){0,2}(tool|app|software|service|solution|alternative|way)|"
        r"looking\s+for\s+(a|an|some|any)\s+(\w+\s+){0,2}(tool|app|software|service|solution|way|alternative)|"
        r"(any|some)\s+recommend(ation)?s?|recommend(ation)?s?\s+for|"
        r"what\s+(tool|app|software)s?\s+(do|does|are)\s+(you|everyone|people)|"
        r"what\s+(do|does)\s+(you|everyone|people)\s+(all\s+)?use\s+(for|to)|"
        r"how\s+(do|does)\s+(you|everyone|people)\s+(all\s+)?(handle|manage|deal\s+with|track)|"
        r"wish\s+there\s+(was|were)|why\s+isn'?t\s+there|someone\s+should\s+build|would\s+(happily\s+)?pay\s+for|"
        r"alternative\s+to|alternatives\s+to)\b",
        re.I,
    ),
    "mentions_cost_or_time": re.compile(
        r"(\$|€|£)\s?\d[\d,.]*\s*(k|/\s*(mo|month|yr|year|user|seat))?|"
        r"\b\d+\s*(hours?|hrs?|days?)\s+(a|per|each|every)\s+(day|week|month)|"
        r"\b(costs?\s+(us|me)|paying\s+\d|too\s+expensive|overpriced|price\s+increase|waste\s+of\s+(time|money)|"
        r"wasting\s+\d|losing\s+(money|clients|customers|hours))\b",
        re.I,
    ),
    "expresses_frustration": re.compile(
        r"\b(hate|frustrat\w+|nightmare|painful|pain\s+in\s+the|annoying|drives\s+me\s+(crazy|nuts|insane)|"
        r"sick\s+of|tired\s+of|fed\s+up|terrible|awful|horrible|useless|broken|sucks|worst|ridiculous|"
        r"can'?t\s+believe|struggl\w+|headache|clunky|bloated|unusable|garbage)\b",
        re.I,
    ),
}

# Placeholder weights (sum = 10). Tune together after first data review.
_WEIGHTS = {
    "mentions_existing_tool": 2,
    "mentions_diy_workaround": 3,
    "asks_for_recommendation": 3,
    "mentions_cost_or_time": 1,
    "expresses_frustration": 1,
}


@dataclass
class HeuristicResult:
    mentions_existing_tool: bool = False
    mentions_diy_workaround: bool = False
    asks_for_recommendation: bool = False
    mentions_cost_or_time: bool = False
    expresses_frustration: bool = False
    heuristic_score: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def analyze(text: str | None, title: str | None = None) -> HeuristicResult:
    blob = f"{title or ''}\n{text or ''}"
    r = HeuristicResult()
    score = 0
    for flag, rx in _FLAGS.items():
        hit = bool(rx.search(blob))
        setattr(r, flag, hit)
        if hit:
            score += _WEIGHTS[flag]
    r.heuristic_score = min(score, 10)
    return r


def matches_keywords(text: str, keywords: list[str]) -> str | None:
    """Return the first keyword found in text (case-insensitive), or None. Empty list = match all ('')."""
    if not keywords:
        return ""
    low = text.lower()
    for k in keywords:
        if k and k.lower() in low:
            return k
    return None
