from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from mangum import Mangum
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import os

app = FastAPI(title="Incident IQ", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AlertRequest(BaseModel):
    service: str
    error: str
    logs: str
    metrics: Optional[Dict[str, Any]] = {}

class AnalyzeRequest(BaseModel):
    alert: AlertRequest
    tenant_id: str
    api_key: str

tenants = {
    "demo_corp": {"name": "Demo Corp", "api_keys": ["demo-key-123"], "incidents": []},
    "test_inc": {"name": "Test Inc", "api_keys": ["test-key-456"], "incidents": []}
}

@app.get("/")
def root():
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return {"service": "Incident IQ", "status": "running", "version": "2.0.0"}

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/dashboard")
def dashboard():
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return {"error": "Dashboard not found - make sure public/index.html exists"}

@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    if request.tenant_id not in tenants:
        raise HTTPException(status_code=401, detail="Invalid tenant")
    if request.api_key not in tenants[request.tenant_id]["api_keys"]:
        raise HTTPException(status_code=401, detail="Invalid API key")

    logs = request.alert.logs.lower()

    if "database" in logs or "connection pool" in logs:
        root_cause = "Database connection pool exhaustion"
        confidence = 0.85
        steps = ["Increase max_connections", "Add connection timeout", "Review for leaks"]
        severity = "high"
    elif "memory" in logs or "oom" in logs:
        root_cause = "Out of memory error"
        confidence = 0.90
        steps = ["Increase memory limit", "Run heap profiler", "Add auto-restart"]
        severity = "critical"
    elif "timeout" in logs:
        root_cause = "Service timeout"
        confidence = 0.75
        steps = ["Add caching", "Optimize queries", "Increase timeout"]
        severity = "medium"
    elif "cpu" in logs:
        root_cause = "CPU overload"
        confidence = 0.70
        steps = ["Scale horizontally", "Profile code", "Move batch jobs"]
        severity = "medium"
    elif "disk" in logs or "storage" in logs:
        root_cause = "Disk space exhaustion"
        confidence = 0.80
        steps = ["Clean old logs", "Add disk monitoring", "Increase storage"]
        severity = "high"
    elif "network" in logs or "connection refused" in logs:
        root_cause = "Network connectivity failure"
        confidence = 0.75
        steps = ["Check firewall rules", "Verify DNS", "Test with ping/telnet"]
        severity = "high"
    else:
        root_cause = "Unknown - manual investigation needed"
        confidence = 0.40
        steps = ["Check full logs", "Review recent changes", "Monitor metrics"]
        severity = "medium"

    incident = {
        "id": f"inc-{int(datetime.now().timestamp())}",
        "service": request.alert.service,
        "root_cause": root_cause,
        "confidence": confidence,
        "severity": severity,
        "timestamp": datetime.now().isoformat()
    }
    tenants[request.tenant_id]["incidents"].append(incident)

    return {
        "incident_id": incident["id"],
        "root_cause": root_cause,
        "confidence_score": confidence,
        "remediation_steps": steps,
        "affected_services": [request.alert.service],
        "severity": severity,
        "analysis_time_ms": 45,
        "tenant": request.tenant_id
    }

@app.get("/api/tenant/incidents")
def get_incidents(tenant_id: str, api_key: str, limit: int = 50):
    if tenant_id not in tenants:
        raise HTTPException(status_code=401, detail="Invalid tenant")
    if api_key not in tenants[tenant_id]["api_keys"]:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {
        "tenant_id": tenant_id,
        "incidents": tenants[tenant_id]["incidents"][-limit:]
    }

handler = Mangum(app)
