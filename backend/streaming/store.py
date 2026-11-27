"""Postgres access for the consumer. Same Incident table the REST API writes to."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..core import Incident, SessionLocal


def _session():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not set")
    return SessionLocal()


def exists(incident_id: str) -> bool:
    with _session() as db:
        return db.scalar(select(Incident.id).where(Incident.incident_id == incident_id)) is not None


def save(incident_id: str, tenant_id: str, alert: dict, result: dict, vec: Optional[list]) -> None:
    with _session() as db:
        db.add(Incident(
            incident_id=incident_id,
            tenant_id=tenant_id,
            service=alert["service"],
            error=alert["error"],
            logs=alert.get("logs", ""),
            root_cause=result.get("root_cause", "unknown"),
            confidence=float(result.get("confidence_score", 0)),
            severity=result.get("severity", "unknown"),
            result=result,
            embedding=vec,
        ))
        try:
            db.commit()
        except IntegrityError:  # another worker saved the same alert first: fine
            db.rollback()


def similar(tenant_id: str, vec: Optional[list], k: int = 3) -> list:
    """Closest past incidents for ONE tenant. Empty when there is no embedding."""
    if vec is None:
        return []
    with _session() as db:
        dist = Incident.embedding.cosine_distance(vec)
        rows = db.execute(
            select(Incident, dist.label("d"))
            .where(Incident.tenant_id == tenant_id, Incident.embedding.is_not(None))
            .order_by(dist).limit(k)
        ).all()
        return [
            {"incident_id": i.incident_id, "service": i.service,
             "root_cause": i.root_cause, "similarity": round(1 - d, 4)}
            for i, d in rows
        ]
