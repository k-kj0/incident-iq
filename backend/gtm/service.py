"""Batch ingest: normalize, resolve to one account, merge, keep lineage.

Safe to retry: a record is identified by (tenant, source, source_record_id), so
re-sending a failed batch updates rows instead of duplicating them.
"""
from datetime import datetime, timezone

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import GtmAccount, GtmDeadLetter, GtmRawRecord
from .normalize import normalize_country, normalize_domain, normalize_name
from .resolver import Candidate, Incoming, resolve

log = structlog.get_logger()


class RawAccount(BaseModel):
    source_record_id: str = Field(min_length=1, max_length=128)
    company_name: str = Field(max_length=256)
    website: str | None = None
    contact_email: str | None = None
    country: str | None = None
    employee_count: int | None = Field(None, ge=0)
    owner: str | None = None
    last_touch_at: datetime | None = None
    signals: list[str] = Field(default_factory=list)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _merge_into(account: GtmAccount, rec: RawAccount, domain: str | None,
                country: str | None, cand: Candidate, taken_domains: dict[str, int]) -> None:
    if account.domain is None and domain and taken_domains.get(domain) in (None, account.id):
        account.domain = domain
        cand.domain = domain
        taken_domains[domain] = account.id
    if account.country is None and country:
        account.country = country
        cand.country = country
    if rec.employee_count is not None:
        account.employee_count = rec.employee_count
    if rec.owner and rec.owner.strip():
        owner = rec.owner.strip()
        if owner.lower() not in {o.lower() for o in account.owners}:
            account.owners = [*account.owners, owner]
    new_signals = [s for s in rec.signals if s not in account.signals]
    if new_signals:
        account.signals = [*account.signals, *new_signals]
    if rec.last_touch_at is not None:
        touched = _aware(rec.last_touch_at)
        if account.last_touch_at is None or touched > _aware(account.last_touch_at):
            account.last_touch_at = touched


def ingest_batch(db: Session, tenant_id: str, source: str, records: list[RawAccount]) -> dict:
    accounts = {a.id: a for a in db.scalars(select(GtmAccount).where(GtmAccount.tenant_id == tenant_id))}
    cands = {a.id: Candidate(a.id, a.name_key, a.domain, a.country) for a in accounts.values()}
    taken_domains = {a.domain: a.id for a in accounts.values() if a.domain}
    summary = {"created": 0, "merged": 0, "updated": 0, "flagged_for_review": 0, "rejected": 0}
    results: list[dict] = []

    for rec in records:
        name_key = normalize_name(rec.company_name)
        if not name_key:
            db.add(GtmDeadLetter(tenant_id=tenant_id, source=source,
                                 payload=rec.model_dump(mode="json"),
                                 reason="company_name has no usable characters"))
            summary["rejected"] += 1
            results.append({"source_record_id": rec.source_record_id, "action": "rejected"})
            continue

        domain = normalize_domain(rec.website) or normalize_domain(rec.contact_email)
        country = normalize_country(rec.country)

        existing = db.scalar(select(GtmRawRecord).where(
            GtmRawRecord.tenant_id == tenant_id, GtmRawRecord.source == source,
            GtmRawRecord.source_record_id == rec.source_record_id))

        if existing is not None:
            account = accounts[existing.account_id]
            existing.payload = rec.model_dump(mode="json")
            action = "updated"
            raw = existing
        else:
            decision = resolve(Incoming(name_key, domain, country), list(cands.values()))
            if decision.account_id is not None:
                account = accounts[decision.account_id]
                action = "merged"
            else:
                account = GtmAccount(tenant_id=tenant_id, canonical_name=rec.company_name.strip(),
                                     name_key=name_key, owners=[], signals=[])
                db.add(account)
                db.flush()
                accounts[account.id] = account
                cands[account.id] = Candidate(account.id, name_key, None, None)
                action = "created"
            raw = GtmRawRecord(
                tenant_id=tenant_id, source=source, source_record_id=rec.source_record_id,
                account_id=account.id, payload=rec.model_dump(mode="json"),
                match_method=decision.method, match_score=decision.score,
                needs_review=decision.review_candidate_id is not None,
                review_candidate_id=decision.review_candidate_id)
            db.add(raw)
            if raw.needs_review:
                summary["flagged_for_review"] += 1

        _merge_into(account, rec, domain, country, cands[account.id], taken_domains)
        summary[action] += 1
        results.append({"source_record_id": rec.source_record_id, "action": action,
                        "account_id": account.id, "match_method": raw.match_method,
                        "match_score": raw.match_score, "needs_review": bool(raw.needs_review)})

    db.commit()
    log.info("gtm_ingest", tenant=tenant_id, source=source, **summary)
    return {"summary": summary, "results": results}
