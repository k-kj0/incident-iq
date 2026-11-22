import io
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core import Base, get_session
from backend.quotes import build_quotes_router
from backend.quotes.compare import compare_quotes
from backend.quotes.coverage import normalize_coverage
from backend.quotes.extract import extract_rules
from backend.quotes.llm_extract import extract_llm
from backend.quotes.models import QuoteDocument
from backend.quotes.money import parse_money
from backend.quotes.verify import verify_extraction

H = {"X-Tenant-Id": "demo_corp", "X-Api-Key": "demo-key-123"}
OTHER = {"X-Tenant-Id": "test_inc", "X-Api-Key": "test-key-456"}

# Synthetic sample quotes (not real documents). Carriers word the same covers differently.
QUOTE_A = ["Carrier: Northstar Mutual\n"
           "Commercial General Liability: Limit $2,000,000 Deductible $2,500\n"
           "Cyber Liability: Limit $1M Retention $10,000\n"
           "Total Premium: $18,400\n",
           "Exclusion: war and military action\n"
           "Exclusion: prior known incidents\n"]
QUOTE_B = ["Insurer: Harbor Specialty\n"
           "CGL | Limit $1,000,000 | Deductible $5,000\n"
           "E&O - Limit $3 million\n"
           "Premium: $15,900\n"
           "Exclusion: War and military action\n"
           "Exclusion: contractual liability\n"]

# Hand-labeled truth for the fixture: (canonical coverage, limit, deductible)
TRUTH_A = {"carrier": "Northstar Mutual", "premium": 18400,
           "coverages": {("general_liability", 2_000_000, 2_500), ("cyber", 1_000_000, 10_000)}}
TRUTH_B = {"carrier": "Harbor Specialty", "premium": 15900,
           "coverages": {("general_liability", 1_000_000, 5_000), ("professional_liability", 3_000_000, None)}}


def _flat(ex):
    return {"carrier": ex["carrier"]["value"], "premium": ex["premium"]["value"],
            "coverages": {(c["canonical"], c["limit"]["value"],
                           c["deductible"]["value"] if c["deductible"] else None) for c in ex["coverages"]}}


def test_money_formats():
    assert parse_money("$1,000,000") == 1_000_000
    assert parse_money("Limit $1M") == 1_000_000
    assert parse_money("$3 million") == 3_000_000
    assert parse_money("$1.5M") == 1_500_000
    assert parse_money("$5,000.") == 5000
    assert parse_money("no money here") is None


def test_coverage_labels_map_to_one_name_and_unknowns_stay_unmapped():
    for label in ["Commercial General Liability", "CGL", "General Liability"]:
        assert normalize_coverage(label) == "general_liability"
    for label in ["E&O", "Errors & Omissions", "Professional Indemnity"]:
        assert normalize_coverage(label) == "professional_liability"
    assert normalize_coverage("Cyber Liabilty") == "cyber"          # typo, long enough for fuzzy
    assert normalize_coverage("Pet Insurance") is None
    assert normalize_coverage("DO") is None                          # short labels never match fuzzily


def test_extraction_accuracy_on_labeled_fixture_and_every_value_verifies():
    """The regression gate: if extraction changes, this fails the build."""
    for pages, truth in [(QUOTE_A, TRUTH_A), (QUOTE_B, TRUTH_B)]:
        ex = extract_rules(pages)
        assert _flat(ex) == truth
        checks = verify_extraction(ex, pages)
        assert checks and all(c["ok"] for c in checks)


def test_citations_point_at_the_exact_source_text():
    ex = extract_rules(QUOTE_A)
    cyber = next(c for c in ex["coverages"] if c["canonical"] == "cyber")
    cite = cyber["limit"]["cite"]
    assert QUOTE_A[cite["page"] - 1][cite["start"]:cite["end"]] == "$1M" == cite["text"]


def test_checker_catches_a_hallucinated_number():
    ex = extract_rules(QUOTE_A)
    ex["coverages"][1]["limit"]["value"] = 5_000_000          # model "invented" a bigger limit
    failed = [c for c in verify_extraction(ex, QUOTE_A) if not c["ok"]]
    assert [f["field"] for f in failed] == ["cyber.limit#1"]
    assert "does not match" in failed[0]["reason"]


def test_checker_catches_a_citation_that_is_not_in_the_document():
    ex = extract_rules(QUOTE_A)
    ex["premium"]["cite"]["text"] = "$99,999"
    ex["exclusions"][0]["cite"]["page"] = 7
    reasons = {c["field"]: c["reason"] for c in verify_extraction(ex, QUOTE_A) if not c["ok"]}
    assert reasons["premium"] == "cited text does not match the document"
    assert reasons["exclusion#0"] == "cited page does not exist"


def test_llm_claims_are_rejected_unless_the_source_says_so():
    fake = {"carrier": {"value": "Northstar Mutual", "snippet": "Northstar Mutual", "page": 1},
            "premium": {"value": 18400, "snippet": "$18,400", "page": 1},
            "coverages": [
                {"label": "Cyber Liability", "limit": {"value": 1_000_000, "snippet": "$1M", "page": 1},
                 "deductible": {"value": 25_000, "snippet": "$25,000", "page": 1}},   # invented
                {"label": "Property", "limit": {"value": 9_000_000, "snippet": "$1M", "page": 1}}],  # wrong number
            "exclusions": [{"text": "war and military action", "snippet": "war and military action", "page": 2}]}
    ex, rejected = extract_llm(QUOTE_A, lambda prompt: json.dumps(fake))
    assert [c["label"] for c in ex["coverages"]] == ["Cyber Liability"]
    assert ex["coverages"][0]["deductible"] is None
    assert {r["field"] for r in rejected} == {"Cyber Liability.deductible", "Property.limit"}
    assert all(c["ok"] for c in verify_extraction(ex, QUOTE_A))


def _doc(i, name, pages):
    ex = extract_rules(pages)
    failed = [v["field"] for v in verify_extraction(ex, pages) if not v["ok"]]
    return {"id": i, "name": name, "extraction": ex, "failed_fields": failed}


def test_compare_flags_gaps_lower_limits_and_exclusion_differences():
    out = compare_quotes([_doc(1, "Northstar", QUOTE_A), _doc(2, "Harbor", QUOTE_B)])
    rows = {r["coverage"]: r for r in out["rows"]}
    assert set(rows) == {"cyber", "general_liability", "professional_liability"}
    assert any("not quoted by Harbor" in f for f in rows["cyber"]["flags"])
    assert any("not quoted by Northstar" in f for f in rows["professional_liability"]["flags"])
    assert any("lower limit: Harbor" in f and "$2,000,000" in f for f in rows["general_liability"]["flags"])
    assert out["exclusions_only_in"][1] == ["prior known incidents"]      # "war..." is in both
    assert out["exclusions_only_in"][2] == ["contractual liability"]


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[QuoteDocument.__table__])
    Session = sessionmaker(engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    app = FastAPI()
    app.include_router(build_quotes_router())
    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_api_ingest_compare_and_tenant_isolation(client):
    a = client.post("/api/v3/quotes", json={"filename": "a.pdf", "pages": QUOTE_A}, headers=H).json()
    b = client.post("/api/v3/quotes", json={"filename": "b.pdf", "pages": QUOTE_B}, headers=H).json()
    assert a["carrier"] == "Northstar Mutual" and a["coverages"] == 2 and a["unverified_claims"] == 0
    cmp_ = client.post("/api/v3/quotes/compare", json={"quote_ids": [a["id"], b["id"]]}, headers=H).json()
    assert [q["name"] for q in cmp_["quotes"]] == ["Northstar Mutual", "Harbor Specialty"]
    detail = client.get(f"/api/v3/quotes/{a['id']}", headers=H).json()
    assert detail["pages"] == QUOTE_A and detail["extraction"]["premium"]["value"] == 18400
    assert client.get(f"/api/v3/quotes/{a['id']}", headers=OTHER).status_code == 404
    assert client.post("/api/v3/quotes/compare", json={"quote_ids": [a["id"], a["id"]]},
                       headers=H).status_code == 422
    assert client.get("/api/v3/quotes", headers=OTHER).json()["items"] == []


def test_api_requires_auth_and_llm_needs_a_key(client, monkeypatch):
    assert client.get("/api/v3/quotes").status_code == 422
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = client.post("/api/v3/quotes", json={"filename": "a", "pages": QUOTE_A, "extractor": "llm"}, headers=H)
    assert r.status_code == 400
    assert client.get("/api/v3/quotes/ui").status_code == 200


def test_pdf_upload_end_to_end(client):
    pytest.importorskip("pdfplumber")
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for line in QUOTE_A[0].strip().split("\n"):
        c.drawString(50, y, line)
        y -= 20
    c.save()
    r = client.post("/api/v3/quotes/upload", files={"file": ("a.pdf", buf.getvalue(), "application/pdf")},
                    headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["carrier"] == "Northstar Mutual" and body["coverages"] == 2 and body["unverified_claims"] == 0
    bad = client.post("/api/v3/quotes/upload", files={"file": ("x.pdf", b"not a pdf", "application/pdf")}, headers=H)
    assert bad.status_code == 422
