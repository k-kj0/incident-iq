"""Rule-based extraction from page text. Every value carries a citation.

A citation is {page, start, end, text} where text == page_text[start:end].
Pages are 1-indexed; offsets are character offsets into that page's text.
This is the deterministic baseline; llm_extract.py produces the same shape.
"""
import re

from .coverage import normalize_coverage
from .money import find_money

_CARRIER = re.compile(r"^\s*(?:carrier|insurer|underwriter)\s*[:\-]\s*(?P<v>.+?)\s*$", re.I)
_EXCLUSION = re.compile(r"^\s*(?:exclusions?|excluded)\s*[:\-]\s*(?P<v>.+?)\s*$", re.I)
_PREMIUM = re.compile(r"\b(?:total\s+)?premium\b", re.I)
_LIMIT = re.compile(r"\blimit\b", re.I)
_DEDUCTIBLE = re.compile(r"\b(?:deductible|retention|sir)\b", re.I)
_LABEL_TRIM = " \t:-|,/\u2013\u2014"


def make_cite(pages: list[str], page: int, start: int, end: int) -> dict:
    return {"page": page, "start": start, "end": end, "text": pages[page - 1][start:end]}


def _lines(text: str):
    pos = 0
    for line in text.split("\n"):
        yield pos, line
        pos += len(line) + 1


def _money_claim(pages, page, offset, line, after: int):
    found = find_money(line, after)
    if not found:
        return None
    value, s, e = found
    return {"value": value, "cite": make_cite(pages, page, offset + s, offset + e)}


def extract_rules(pages: list[str]) -> dict:
    out: dict = {"carrier": None, "premium": None, "coverages": [], "exclusions": []}
    for pno, text in enumerate(pages, start=1):
        for offset, line in _lines(text):
            m = _CARRIER.match(line)
            if m and out["carrier"] is None:
                out["carrier"] = {"value": m.group("v"),
                                  "cite": make_cite(pages, pno, offset + m.start("v"), offset + m.end("v"))}
                continue
            m = _EXCLUSION.match(line)
            if m:
                out["exclusions"].append({"text": m.group("v"),
                                          "cite": make_cite(pages, pno, offset + m.start("v"), offset + m.end("v"))})
                continue
            lim = _LIMIT.search(line)
            if lim:
                label = line[:lim.start()].strip(_LABEL_TRIM)
                limit = _money_claim(pages, pno, offset, line, lim.end())
                if not label or limit is None:
                    continue
                ded = _DEDUCTIBLE.search(line, lim.end())
                out["coverages"].append({
                    "label": label,
                    "canonical": normalize_coverage(label),
                    "limit": limit,
                    "deductible": _money_claim(pages, pno, offset, line, ded.end()) if ded else None,
                })
                continue
            prem = _PREMIUM.search(line)
            if prem and out["premium"] is None:
                claim = _money_claim(pages, pno, offset, line, prem.end())
                if claim:
                    out["premium"] = claim
    return out
