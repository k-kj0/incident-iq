"""LLM extraction whose claims must survive the citation checker.

The model is asked for each value plus the exact text snippet and page it came
from. We then locate that snippet ourselves. A claim whose snippet is not on
the page, or whose number disagrees with its snippet, is rejected, not shown.
`call_llm` is injectable so tests run offline; the default calls Gemini.
"""
import json
import os

import httpx

from .coverage import normalize_coverage
from .extract import make_cite
from .money import parse_money

PROMPT = """You extract data from an insurance quote. Return ONLY JSON:
{{"carrier": {{"value": str, "snippet": str, "page": int}},
 "premium": {{"value": int, "snippet": str, "page": int}},
 "coverages": [{{"label": str,
   "limit": {{"value": int, "snippet": str, "page": int}},
   "deductible": {{"value": int, "snippet": str, "page": int}} or null}}],
 "exclusions": [{{"text": str, "snippet": str, "page": int}}]}}
"snippet" must be copied exactly from the document. Do not infer or guess values.
If a field is not in the document, omit it.

DOCUMENT:
{document}"""


def gemini_json(prompt: str) -> str:
    key = os.getenv("GEMINI_API_KEY", "")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0}},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def locate(pages: list[str], page, snippet) -> dict | None:
    """Find the snippet on the claimed page (any page as a fallback). None if absent."""
    if not isinstance(snippet, str) or not snippet.strip():
        return None
    order = [page - 1] if isinstance(page, int) and 1 <= page <= len(pages) else []
    order += [i for i in range(len(pages)) if i not in order]
    for i in order:
        at = pages[i].find(snippet)
        if at >= 0:
            return make_cite(pages, i + 1, at, at + len(snippet))
    return None


def extract_llm(pages: list[str], call_llm=gemini_json) -> tuple[dict, list[dict]]:
    doc = "\n\n".join(f"[page {i}]\n{t}" for i, t in enumerate(pages, start=1))
    raw = json.loads(call_llm(PROMPT.format(document=doc)))
    rejected: list[dict] = []

    def money(field, c):
        if not isinstance(c, dict):
            return None
        cite = locate(pages, c.get("page"), c.get("snippet"))
        if cite is None:
            rejected.append({"field": field, "reason": "snippet not found in document", "claim": c})
            return None
        if parse_money(cite["text"]) != c.get("value"):
            rejected.append({"field": field, "reason": "number does not match its snippet", "claim": c})
            return None
        return {"value": c["value"], "cite": cite}

    def text(field, c, key="value"):
        if not isinstance(c, dict):
            return None
        cite = locate(pages, c.get("page"), c.get("snippet"))
        if cite is None or str(c.get(key, "")).strip().lower() not in cite["text"].lower():
            rejected.append({"field": field, "reason": "text not supported by its snippet", "claim": c})
            return None
        return {key: c[key], "cite": cite}

    out = {"carrier": text("carrier", raw.get("carrier")),
           "premium": money("premium", raw.get("premium")),
           "coverages": [], "exclusions": []}
    for cov in raw.get("coverages") or []:
        label = str(cov.get("label", "")).strip()
        limit = money(f"{label}.limit", cov.get("limit"))
        if not label or limit is None:
            continue
        out["coverages"].append({"label": label, "canonical": normalize_coverage(label),
                                 "limit": limit, "deductible": money(f"{label}.deductible", cov.get("deductible"))})
    for ex in raw.get("exclusions") or []:
        item = text("exclusion", ex, key="text")
        if item:
            out["exclusions"].append(item)
    return out, rejected
