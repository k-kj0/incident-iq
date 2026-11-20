from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core import Base, get_session
from backend.gtm import build_gtm_router
from backend.gtm.models import GtmAccount, GtmDeadLetter, GtmRawRecord

H = {"X-Tenant-Id": "demo_corp", "X-Api-Key": "demo-key-123"}
OTHER = {"X-Tenant-Id": "test_inc", "X-Api-Key": "test-key-456"}


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[
        GtmAccount.__table__, GtmRawRecord.__table__, GtmDeadLetter.__table__])
    Session = sessionmaker(engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    app = FastAPI()
    app.include_router(build_gtm_router())
    app.dependency_overrides[get_session] = override
    return TestClient(app)


def _ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _ingest(client, source, records, headers=H):
    return client.post("/api/v3/gtm/ingest", json={"source": source, "records": records},
                       headers=headers)


def test_auth_required(client):
    assert client.get("/api/v3/gtm/call-list").status_code == 422
    bad = {"X-Tenant-Id": "demo_corp", "X-Api-Key": "nope"}
    assert client.get("/api/v3/gtm/call-list", headers=bad).status_code == 401
    cross = {"X-Tenant-Id": "test_inc", "X-Api-Key": "demo-key-123"}
    assert client.get("/api/v3/gtm/call-list", headers=cross).status_code == 401


def test_two_reps_same_company_become_one_account(client):
    r1 = _ingest(client, "anna_sheet", [
        {"source_record_id": "r1", "company_name": "Acme GmbH", "website": "https://www.acme.de",
         "country": "DE", "employee_count": 120, "owner": "anna",
         "signals": ["hiring_security_role"], "last_touch_at": _ago(45)}]).json()
    r2 = _ingest(client, "raj_hubspot", [
        {"source_record_id": "991", "company_name": "ACME", "contact_email": "cto@acme.de",
         "owner": "raj", "signals": ["customer_asked_for_certification"],
         "last_touch_at": _ago(40)}]).json()
    assert r1["summary"]["created"] == 1
    assert r2["summary"]["merged"] == 1
    assert r2["results"][0]["match_method"] == "domain"
    assert r1["results"][0]["account_id"] == r2["results"][0]["account_id"]

    acc = client.get(f"/api/v3/gtm/accounts/{r1['results'][0]['account_id']}", headers=H).json()
    assert sorted(acc["owners"]) == ["anna", "raj"]
    assert set(acc["signals"]) == {"hiring_security_role", "customer_asked_for_certification"}
    assert acc["recommendation"] == "coordinate"
    assert [x["source"] for x in acc["lineage"]] == ["anna_sheet", "raj_hubspot"]

    coord = client.get("/api/v3/gtm/call-list", params={"recommendation": "coordinate"}, headers=H).json()
    assert coord["items"][0]["name"] == "Acme GmbH"
    assert "anna, raj" in coord["items"][0]["why"][0]
    assert client.get("/api/v3/gtm/call-list", headers=H).json()["items"] == []


def test_ingest_is_idempotent_so_failed_batches_can_be_resent(client):
    rec = {"source_record_id": "r1", "company_name": "Orbit Security", "website": "orbitsec.com",
           "country": "FR", "employee_count": 80, "owner": "anna"}
    assert _ingest(client, "s", [rec]).json()["summary"]["created"] == 1
    again = _ingest(client, "s", [{**rec, "employee_count": 95}]).json()
    assert again["summary"] == {"created": 0, "merged": 0, "updated": 1,
                                "flagged_for_review": 0, "rejected": 0}
    acc = client.get(f"/api/v3/gtm/accounts/{again['results'][0]['account_id']}", headers=H).json()
    assert acc["employee_count"] == 95 and len(acc["lineage"]) == 1


def test_call_list_ranks_with_reasons_and_skips_recently_touched(client):
    _ingest(client, "s", [
        {"source_record_id": "1", "company_name": "Hot Co", "website": "hot.io", "country": "DE",
         "employee_count": 150, "signals": ["customer_asked_for_certification", "hiring_security_role"]},
        {"source_record_id": "2", "company_name": "Warm Co", "website": "warm.io", "country": "NL",
         "employee_count": 60, "signals": ["hiring_security_role", "recent_funding"]},
        {"source_record_id": "3", "company_name": "Busy Co", "website": "busy.io", "country": "DE",
         "employee_count": 150, "signals": ["customer_asked_for_certification"],
         "owner": "raj", "last_touch_at": _ago(2)},
        {"source_record_id": "4", "company_name": "Cold Co", "website": "cold.io", "country": "US",
         "employee_count": 5000},
    ])
    items = client.get("/api/v3/gtm/call-list", headers=H).json()["items"]
    assert [i["name"] for i in items] == ["Hot Co", "Warm Co"]
    assert items[0]["score"] == 90
    assert items[0]["why"][0].startswith("one of their customers asked")
    wait = client.get("/api/v3/gtm/call-list", params={"recommendation": "wait"}, headers=H).json()
    assert [i["name"] for i in wait["items"]] == ["Busy Co"]


def test_near_duplicates_go_to_review_queue_not_merged(client):
    res = _ingest(client, "s", [
        {"source_record_id": "1", "company_name": "Stripe", "website": "stripe.com", "country": "US"},
        {"source_record_id": "2", "company_name": "Stripes", "website": "stripes.com", "country": "US"},
    ]).json()
    assert res["summary"]["created"] == 2 and res["summary"]["flagged_for_review"] == 1
    dupes = client.get("/api/v3/gtm/duplicates", headers=H).json()["items"]
    assert dupes[0]["name"] == "Stripes" and dupes[0]["possible_match_name"] == "Stripe"


def test_unusable_rows_go_to_dead_letters_without_failing_the_batch(client):
    res = _ingest(client, "s", [
        {"source_record_id": "1", "company_name": "---"},
        {"source_record_id": "2", "company_name": "Real Co", "website": "real.io"},
    ]).json()
    assert res["summary"]["rejected"] == 1 and res["summary"]["created"] == 1
    dl = client.get("/api/v3/gtm/dead-letters", headers=H).json()["items"]
    assert dl[0]["payload"]["source_record_id"] == "1" and "usable" in dl[0]["reason"]


def test_tenants_are_isolated(client):
    _ingest(client, "s", [{"source_record_id": "1", "company_name": "Acme", "website": "acme.de"}])
    aid = client.get("/api/v3/gtm/call-list", params={"recommendation": "nurture"},
                     headers=H).json()["items"][0]["account_id"]
    assert client.get(f"/api/v3/gtm/accounts/{aid}", headers=OTHER).status_code == 404
    assert client.get("/api/v3/gtm/call-list", params={"recommendation": "nurture"},
                      headers=OTHER).json()["items"] == []
