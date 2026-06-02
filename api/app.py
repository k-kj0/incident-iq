from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

app = FastAPI(title="Incident IQ", version="1.0.0")

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
    metrics: Optional[Dict] = {}

class AnalyzeRequest(BaseModel):
    alert: AlertRequest
    tenant_id: str
    api_key: str

tenants = {
    "demo_corp": {"name": "Demo Corp", "api_keys": ["demo-key-123"]}
}

@app.get("/")
def root():
    return {"service": "Incident IQ", "status": "running"}

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    if request.tenant_id not in tenants:
        raise HTTPException(401, "Invalid tenant")
    if request.api_key not in tenants[request.tenant_id]["api_keys"]:
        raise HTTPException(401, "Invalid API key")
    
    logs = request.alert.logs.lower()
    
    if "database" in logs:
        root_cause = "Database connection issue"
        confidence = 0.85
        steps = ["Check database", "Increase pool size"]
    else:
        root_cause = "Unknown issue"
        confidence = 0.40
        steps = ["Check logs", "Review changes"]
    
    return {
        "incident_id": f"inc-{int(datetime.now().timestamp())}",
        "root_cause": root_cause,
        "confidence_score": confidence,
        "remediation_steps": steps,
        "severity": "high"
    }
