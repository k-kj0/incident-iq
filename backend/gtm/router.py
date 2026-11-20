import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import TENANT_KEYS, get_session
from .models import GtmAccount, GtmDeadLetter, GtmRawRecord
from .scoring import score_account
from .service import RawAccount, ingest_batch


class IngestRequest(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    records: list[RawAccount] = Field(min_length=1, max_length=500)


def auth(x_tenant_id: str = Header(...), x_api_key: str = Header(...)) -> str:
    expected = TENANT_KEYS.get(x_tenant_id)
    if not expected or not hmac.compare_digest(expected.encode(), x_api_key.encode()):
        raise HTTPException(status_code=401, detail="invalid tenant or api key")
    return x_tenant_id


def _score(a: GtmAccount, now: datetime):
    return score_account(signals=a.signals or [], country=a.country,
                         employee_count=a.employee_count, owners=a.owners or [],
                         last_touch_at=a.last_touch_at, now=now)


def build_gtm_router() -> APIRouter:
    r = APIRouter(prefix="/api/v3/gtm", tags=["gtm"])

    @r.post("/ingest")
    def ingest(req: IngestRequest, tenant: str = Depends(auth),
               db: Session = Depends(get_session)):
        return ingest_batch(db, tenant, req.source, req.records)

    @r.get("/call-list")
    def call_list(limit: int = Query(10, ge=1, le=100),
                  recommendation: str = Query("call_today"),
                  tenant: str = Depends(auth), db: Session = Depends(get_session)):
        now = datetime.now(timezone.utc)
        rows = []
        for a in db.scalars(select(GtmAccount).where(GtmAccount.tenant_id == tenant)):
            s = _score(a, now)
            if s.recommendation == recommendation:
                rows.append((a, s))
        rows.sort(key=lambda x: (-x[1].score, x[0].canonical_name))
        return {"recommendation": recommendation, "items": [
            {"account_id": a.id, "name": a.canonical_name, "domain": a.domain,
             "country": a.country, "employee_count": a.employee_count,
             "score": s.score, "why": s.reasons, "owners": a.owners,
             "last_touch_at": a.last_touch_at}
            for a, s in rows[:limit]]}

    @r.get("/accounts/{account_id}")
    def account_detail(account_id: int, tenant: str = Depends(auth),
                       db: Session = Depends(get_session)):
        a = db.get(GtmAccount, account_id)
        if a is None or a.tenant_id != tenant:
            raise HTTPException(status_code=404, detail="account not found")
        s = _score(a, datetime.now(timezone.utc))
        lineage = db.scalars(select(GtmRawRecord).where(GtmRawRecord.account_id == a.id)
                             .order_by(GtmRawRecord.id)).all()
        return {
            "account_id": a.id, "name": a.canonical_name, "domain": a.domain,
            "country": a.country, "employee_count": a.employee_count,
            "owners": a.owners, "signals": a.signals, "last_touch_at": a.last_touch_at,
            "score": s.score, "recommendation": s.recommendation, "why": s.reasons,
            "lineage": [{"source": x.source, "source_record_id": x.source_record_id,
                         "match_method": x.match_method, "match_score": x.match_score,
                         "as_received": x.payload} for x in lineage],
        }

    @r.get("/duplicates")
    def possible_duplicates(tenant: str = Depends(auth), db: Session = Depends(get_session)):
        flagged = db.scalars(select(GtmRawRecord).where(
            GtmRawRecord.tenant_id == tenant, GtmRawRecord.needs_review.is_(True))).all()
        names = {a.id: a.canonical_name for a in db.scalars(
            select(GtmAccount).where(GtmAccount.tenant_id == tenant))}
        return {"items": [
            {"account_id": x.account_id, "name": names.get(x.account_id),
             "possible_match_account_id": x.review_candidate_id,
             "possible_match_name": names.get(x.review_candidate_id),
             "similarity": x.match_score, "source": x.source,
             "source_record_id": x.source_record_id} for x in flagged]}

    @r.get("/dead-letters")
    def dead_letters(tenant: str = Depends(auth), db: Session = Depends(get_session)):
        rows = db.scalars(select(GtmDeadLetter).where(GtmDeadLetter.tenant_id == tenant)
                          .order_by(GtmDeadLetter.id.desc()).limit(100)).all()
        return {"items": [{"source": x.source, "reason": x.reason, "payload": x.payload,
                           "created_at": x.created_at} for x in rows]}

    return r
