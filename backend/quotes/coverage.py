"""Map each carrier's wording for a coverage onto one standard name.

Carriers call the same cover different things ("E&O" vs "Professional Liability"),
so a side-by-side comparison is meaningless until labels are normalized.
Anything we cannot map confidently is returned as None, never guessed.
"""
import difflib
import re

ALIASES: dict[str, list[str]] = {
    "general_liability": ["general liability", "commercial general liability", "cgl", "gl", "public liability"],
    "property": ["property", "commercial property", "building and contents",
                 "building and business personal property"],
    "cyber": ["cyber", "cyber liability", "cyber and privacy liability", "data breach",
              "network security and privacy liability"],
    "professional_liability": ["professional liability", "errors and omissions", "errors omissions",
                               "e and o", "eo", "professional indemnity"],
    "workers_comp": ["workers compensation", "workers comp", "workers compensation and employers liability"],
    "umbrella": ["umbrella", "umbrella liability", "excess liability", "excess"],
    "directors_officers": ["directors and officers", "d and o", "management liability"],
    "business_interruption": ["business interruption", "business income", "loss of income"],
}
_LOOKUP = {alias: canon for canon, aliases in ALIASES.items() for alias in aliases}
FUZZY_MIN = 0.88
FUZZY_MIN_LEN = 8  # short labels never match fuzzily ("do" vs "go")


def clean_label(label: str) -> str:
    s = label.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(s.split())


def normalize_coverage(label: str) -> str | None:
    key = clean_label(label)
    if not key:
        return None
    if key in _LOOKUP:
        return _LOOKUP[key]
    if len(key) >= FUZZY_MIN_LEN:
        best, best_score = None, 0.0
        for alias, canon in _LOOKUP.items():
            if len(alias) < FUZZY_MIN_LEN:
                continue
            score = difflib.SequenceMatcher(None, key, alias).ratio()
            if score > best_score:
                best, best_score = canon, score
        if best_score >= FUZZY_MIN:
            return best
    return None
