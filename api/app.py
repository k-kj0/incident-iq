cat > api/app.py << 'EOF'
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

app = FastAPI(title="Incident IQ with NVIDIA Nemotron", version="2.0.0")

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
async def root():
    return {
        "service": "Incident IQ",
        "version": "2.0.0",
        "status": "operational",
        "endpoints": ["/health", "/api/analyze", "/api/tenant/incidents"],
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "tenants": len(tenants),
        "timestamp": datetime.now().isoformat(),
        "model": "NVIDIA Nemotron (Simulated)"
    }

@app.post("/api/analyze")
async def analyze_incident(request: AnalyzeRequest):
    if request.tenant_id not in tenants:
        raise HTTPException(status_code=401, detail="Invalid tenant")
    if request.api_key not in tenants[request.tenant_id]["api_keys"]:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    logs = request.alert.logs.lower()
    service = request.alert.service
    
    if "database" in logs or "connection pool" in logs:
        root_cause = "Database connection pool exhaustion"
        confidence = 0.85
        remediation = ["Increase max_connections", "Add connection timeout", "Review for leaks"]
        severity = "high"
    elif "memory" in logs or "oom" in logs:
        root_cause = "Application memory leak"
        confidence = 0.90
        remediation = ["Increase memory limit", "Run heap profiler", "Add auto-restart"]
        severity = "critical"
    elif "timeout" in logs:
        root_cause = "Service timeout"
        confidence = 0.75
        remediation = ["Add caching", "Optimize queries", "Increase timeout"]
        severity = "medium"
    else:
        root_cause = "Unable to determine automatically"
        confidence = 0.40
        remediation = ["Collect full logs", "Check dependencies", "Review changes"]
        severity = "medium"
    
    incident = {
        "id": f"inc-{int(datetime.now().timestamp())}",
        "service": service,
        "root_cause": root_cause,
        "confidence": confidence,
        "severity": severity,
        "timestamp": datetime.now().isoformat()
    }
    tenants[request.tenant_id]["incidents"].append(incident)
    
    return {
        "success": True,
        "incident_id": incident["id"],
        "root_cause": root_cause,
        "confidence_score": confidence,
        "remediation_steps": remediation,
        "affected_services": [service],
        "severity": severity,
        "analysis_time_ms": 45,
        "tenant": request.tenant_id
    }

@app.get("/api/tenant/incidents")
async def get_incidents(tenant_id: str, api_key: str, limit: int = 50):
    if tenant_id not in tenants:
        raise HTTPException(status_code=401, detail="Invalid tenant")
    if api_key not in tenants[tenant_id]["api_keys"]:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    incidents = tenants[tenant_id]["incidents"][-limit:]
    return {
        "tenant_id": tenant_id,
        "tenant_name": tenants[tenant_id]["name"],
        "incident_count": len(incidents),
        "incidents": incidents
    }

# This is the handler for Vercel
handler = Mangum(app)
EOF
