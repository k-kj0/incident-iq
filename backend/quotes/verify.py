"""Citation checker: a value is only trusted if its cited text really says it.

Works on the output of ANY extractor (rules or LLM). It does not ask the model
whether it is right; it re-reads the source text and compares.
"""
from .money import parse_money


def check_cite(pages: list[str], cite: dict | None) -> str | None:
    """Return a failure reason, or None if the citation points at real text."""
    if not cite:
        return "no citation"
    page, start, end = cite.get("page"), cite.get("start"), cite.get("end")
    if not isinstance(page, int) or not 1 <= page <= len(pages):
        return "cited page does not exist"
    text = pages[page - 1]
    if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text)):
        return "cited span is outside the page"
    if text[start:end] != cite.get("text"):
        return "cited text does not match the document"
    return None


def check_money(pages, claim: dict | None) -> str | None:
    reason = check_cite(pages, claim.get("cite") if claim else None)
    if reason:
        return reason
    if parse_money(claim["cite"]["text"]) != claim["value"]:
        return "number does not match the cited text"
    return None


def check_text(pages, claim: dict | None, key: str = "value") -> str | None:
    reason = check_cite(pages, claim.get("cite") if claim else None)
    if reason:
        return reason
    if str(claim[key]).strip().lower() not in claim["cite"]["text"].lower():
        return "text does not match the cited text"
    return None


def verify_extraction(extraction: dict, pages: list[str]) -> list[dict]:
    """One entry per claim: {field, ok, reason}. Used to flag, never to hide."""
    results: list[dict] = []

    def add(field, reason):
        results.append({"field": field, "ok": reason is None, "reason": reason})

    if extraction.get("carrier"):
        add("carrier", check_text(pages, extraction["carrier"]))
    if extraction.get("premium"):
        add("premium", check_money(pages, extraction["premium"]))
    for i, cov in enumerate(extraction.get("coverages", [])):
        name = cov.get("canonical") or f"unmapped:{cov['label']}"
        add(f"{name}.limit#{i}", check_money(pages, cov.get("limit")))
        if cov.get("deductible"):
            add(f"{name}.deductible#{i}", check_money(pages, cov["deductible"]))
    for i, ex in enumerate(extraction.get("exclusions", [])):
        add(f"exclusion#{i}", check_text(pages, ex, key="text"))
    return results
