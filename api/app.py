import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from mangum import Mangum
from pydantic import BaseModel

app = FastAPI(title="Incident IQ", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class AlertRequest(BaseModel):
    service: str
    error: str
    logs: str
    metrics: Optional[Dict[str, Any]] = {}


class AnalyzeRequest(BaseModel):
    alert: AlertRequest
    tenant_id: str
    api_key: str


# ---------------------------------------------------------------------------
# In-memory tenant store
# NOTE: this resets on every cold start / redeploy. Fine for a demo,
# swap for Postgres/Redis before treating this as persistent.
# ---------------------------------------------------------------------------

tenants: Dict[str, Dict[str, Any]] = {
    "demo_corp": {"name": "Demo Corp", "api_keys": ["demo-key-123"], "incidents": []},
    "test_inc": {"name": "Test Inc", "api_keys": ["test-key-456"], "incidents": []},
}


# ---------------------------------------------------------------------------
# Reasoning engine
# This used to sit unused at the bottom of the file. It's now the thing
# that actually powers /api/analyze.
# ---------------------------------------------------------------------------

@dataclass
class IncidentAnalysis:
    root_cause: str
    confidence_score: float
    remediation_steps: List[str]
    affected_services: List[str]
    severity: str
    reasoning_trace: List[str]


class NemotronReasoningEngine:
    """
    Rule-based reasoning engine used for the live demo.
    Structured to be swapped for an actual Nemotron-backed call later
    (see reasoning_trace, which mirrors what a model's chain-of-thought
    output would look like).
    """

    def analyze_incident(self, logs: str, service: str) -> IncidentAnalysis:
        lower_logs = logs.lower()
        trace: List[str] = []

        if "database" in lower_logs or "connection pool" in lower_logs:
            trace += ["Found database/connection-pool keyword", "Matched connection pool exhaustion pattern"]
            return IncidentAnalysis(
                root_cause="Database connection pool exhaustion",
                confidence_score=0.85,
                remediation_steps=[
                    "Increase max_connections in database config",
                    "Add connection timeout and retry logic",
                    "Review code for connection leaks",
                    "Implement connection pooling monitoring",
                ],
                affected_services=[service],
                severity="high",
                reasoning_trace=trace,
            )

        if "memory" in lower_logs or "oom" in lower_logs:
            trace += ["Found memory/OOM keyword", "Matched out-of-memory pattern"]
            return IncidentAnalysis(
                root_cause="Out of memory error",
                confidence_score=0.90,
                remediation_steps=[
                    "Increase memory limit",
                    "Run heap profiler",
                    "Add auto-restart on OOM",
                ],
                affected_services=[service],
                severity="critical",
                reasoning_trace=trace,
            )

        if "timeout" in lower_logs:
            trace += ["Found timeout keyword", "Matched service timeout pattern"]
            return IncidentAnalysis(
                root_cause="Service timeout",
                confidence_score=0.75,
                remediation_steps=["Add caching", "Optimize queries", "Increase timeout threshold"],
                affected_services=[service],
                severity="medium",
                reasoning_trace=trace,
            )

        if "cpu" in lower_logs:
            trace += ["Found CPU keyword", "Matched CPU overload pattern"]
            return IncidentAnalysis(
                root_cause="CPU overload",
                confidence_score=0.70,
                remediation_steps=["Scale horizontally", "Profile code", "Move batch jobs off peak hours"],
                affected_services=[service],
                severity="medium",
                reasoning_trace=trace,
            )

        if "disk" in lower_logs or "storage" in lower_logs:
            trace += ["Found disk/storage keyword", "Matched disk exhaustion pattern"]
            return IncidentAnalysis(
                root_cause="Disk space exhaustion",
                confidence_score=0.80,
                remediation_steps=["Clean old logs", "Add disk monitoring", "Increase storage allocation"],
                affected_services=[service],
                severity="high",
                reasoning_trace=trace,
            )

        if "network" in lower_logs or "connection refused" in lower_logs:
            trace += ["Found network keyword", "Matched network connectivity pattern"]
            return IncidentAnalysis(
                root_cause="Network connectivity failure",
                confidence_score=0.75,
                remediation_steps=["Check firewall rules", "Verify DNS resolution", "Test with ping/telnet"],
                affected_services=[service],
                severity="high",
                reasoning_trace=trace,
            )

        trace.append("No known pattern matched")
        return IncidentAnalysis(
            root_cause="Unknown — manual investigation needed",
            confidence_score=0.40,
            remediation_steps=["Check full logs", "Review recent changes", "Monitor metrics"],
            affected_services=[service],
            severity="medium",
            reasoning_trace=trace,
        )


engine = NemotronReasoningEngine()

# ---------------------------------------------------------------------------
# Static HTML
# ---------------------------------------------------------------------------

_PUBLIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
_INDEX_PATH = os.path.join(_PUBLIC_DIR, "index.html")


def _load_dashboard_html() -> str:
    with open(_INDEX_PATH, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/")
def root():
    return HTMLResponse(content=_load_dashboard_html(), status_code=200)


@app.get("/dashboard")
def dashboard():
    return HTMLResponse(content=_load_dashboard_html(), status_code=200)


@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    if request.tenant_id not in tenants:
        raise HTTPException(status_code=401, detail="Invalid tenant")
    if request.api_key not in tenants[request.tenant_id]["api_keys"]:
        raise HTTPException(status_code=401, detail="Invalid API key")

    analysis = engine.analyze_incident(request.alert.logs, request.alert.service)

    incident = {
        "id": f"inc-{int(datetime.now().timestamp())}",
        "service": request.alert.service,
        "root_cause": analysis.root_cause,
        "confidence": analysis.confidence_score,
        "severity": analysis.severity,
        "timestamp": datetime.now().isoformat(),
    }
    tenants[request.tenant_id]["incidents"].append(incident)

    return {
        "incident_id": incident["id"],
        "root_cause": analysis.root_cause,
        "confidence_score": analysis.confidence_score,
        "remediation_steps": analysis.remediation_steps,
        "affected_services": analysis.affected_services,
        "severity": analysis.severity,
        "reasoning_trace": analysis.reasoning_trace,
        "analysis_time_ms": 45,
        "tenant": request.tenant_id,
    }


@app.get("/api/tenant/incidents")
def get_incidents(tenant_id: str, api_key: str, limit: int = 50):
    if tenant_id not in tenants:
        raise HTTPException(status_code=401, detail="Invalid tenant")
    if api_key not in tenants[tenant_id]["api_keys"]:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return {
        "tenant_id": tenant_id,
        "incidents": tenants[tenant_id]["incidents"][-limit:],
    }


# Vercel's Python runtime looks for a top-level variable literally named
# "app", "application", or "handler". This must stay as-is.
handler = Mangum(app)
