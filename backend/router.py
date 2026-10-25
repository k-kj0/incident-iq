import hashlib
import hmac
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .cache import cached
from .db import get_session
from .embeddings import embed
from .models import Incident
from .settings import TENANT_KEYS

log = structlog.get_logger()


class Alert(BaseModel):
    service: str
    error: str
    logs: str = ""
    metrics: dict = Field(default_factory=dict)


class AnalyzeRequest(BaseModel):
    alert: Alert
    tenant_id: str
    api_key: str


class SimilarRequest(BaseModel):
    tenant_id: str
    api_key: str
    query: str
    k: int = Field(5, ge=1, le=20)


def _auth(tenant_id: str, api_key: str) -> None:
    expected = TENANT_KEYS.get(tenant_id)
    if not expected or not hmac.compare_digest(expected, api_key):
        raise HTTPException(status_code=401, detail="invalid tenant or api key")


def build_router(analyze_fn) -> APIRouter:
    r = APIRouter(prefix="/api/v2", tags=["v2"])

    @r.get("/ready")
    def ready(db: Session = Depends(get_session)):
        db.execute(text("SELECT 1"))
        return {"status": "ready"}

    @r.post("/analyze")
    def analyze(req: AnalyzeRequest, db: Session = Depends(get_session)):
        _auth(req.tenant_id, req.api_key)
        started = time.perf_counter()
        result = analyze_fn(req.alert.model_dump())
        incident_id = result.get("incident_id") or f"inc-{uuid.uuid4().hex[:10]}"
        result["incident_id"] = incident_id
        vec = embed(f"{req.alert.service}\n{req.alert.error}\n{req.alert.logs}")
        db.add(
            Incident(
                incident_id=incident_id,
                tenant_id=req.tenant_id,
                service=req.alert.service,
                error=req.alert.error,
                logs=req.alert.logs,
                root_cause=result.get("root_cause", "unknown"),
                confidence=float(result.get("confidence_score", 0)),
                severity=result.get("severity", "unknown"),
                result=result,
                embedding=vec,
            )
        )
        db.commit()
        log.info("incident_saved", tenant=req.tenant_id, incident_id=incident_id,
                 embedded=vec is not None,
                 ms=round((time.perf_counter() - started) * 1000, 1))
        return result

    @r.get("/incidents")
    def list_incidents(tenant_id: str, api_key: str, limit: int = 20, offset: int = 0,
                       db: Session = Depends(get_session)):
        _auth(tenant_id, api_key)
        limit = max(1, min(limit, 100))
        rows = db.scalars(
            select(Incident).where(Incident.tenant_id == tenant_id)
            .order_by(Incident.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return {"items": [x.result for x in rows], "limit": limit, "offset": offset}

    @r.post("/incidents/similar")
    def similar(req: SimilarRequest, db: Session = Depends(get_session)):
        _auth(req.tenant_id, req.api_key)
        key = "sim:" + hashlib.sha256(
            f"{req.tenant_id}|{req.k}|{req.query}".encode()
        ).hexdigest()

        def compute():
            vec = embed(req.query)
            if vec is None:
                return {"mode": "unavailable", "items": []}
            dist = Incident.embedding.cosine_distance(vec)
            rows = db.execute(
                select(Incident, dist.label("d"))
                .where(Incident.tenant_id == req.tenant_id,
                       Incident.embedding.is_not(None))
                .order_by(dist).limit(req.k)
            ).all()
            return {
                "mode": "vector",
                "items": [
                    {"incident_id": i.incident_id, "service": i.service,
                     "root_cause": i.root_cause, "similarity": round(1 - d, 4)}
                    for i, d in rows
                ],
            }

        # 60s TTL: a just-saved incident can take up to a minute to show in cached results.
        return cached(key, 60, compute)

    return r
