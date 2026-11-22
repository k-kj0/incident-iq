import os

from .extract import extract_rules
from .llm_extract import extract_llm
from .verify import verify_extraction


def pages_from_pdf(data: bytes) -> list[str]:
    """Text per page. Needs a text-based PDF; scanned PDFs return empty pages."""
    import io

    import pdfplumber  # imported lazily so the rest of the app runs without it

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return [(p.extract_text() or "") for p in pdf.pages]


def analyze_pages(pages: list[str], extractor: str = "rules", call_llm=None) -> dict:
    rejected: list[dict] = []
    if extractor == "llm":
        if call_llm is None and not os.getenv("GEMINI_API_KEY"):
            raise ValueError("extractor 'llm' needs GEMINI_API_KEY")
        extraction, rejected = extract_llm(pages, call_llm) if call_llm else extract_llm(pages)
    else:
        extraction = extract_rules(pages)
    verification = verify_extraction(extraction, pages)
    return {"extraction": extraction, "verification": verification, "rejected": rejected,
            "failed_count": sum(1 for v in verification if not v["ok"])}
