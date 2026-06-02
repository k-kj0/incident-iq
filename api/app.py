from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
import os
import json

# Import your modules
import sys
sys.path.append('.')
from adapters.reasoning_adapter import NemotronReasoningEngine, IncidentAnalysis
from adapters.multi_tenant import TenantManager, TenantAwareRAG


# Initialize FastAPI - Vercel will detect this automatically
app = FastAPI(
    title="Incident IQ with NVIDIA Nemotron",
    description="AI-powered root cause analysis for multi-tenant environments",
    version="1.0.0"
)

# CORS for web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances (initialized at startup)
reasoning_engine = None
tenant_manager = None
rag_system = None


class AlertRequest(BaseModel):
    """Incoming alert structure"""
    service: str
    error: str
    logs: str
    metrics: Optional[Dict[str, Any]] = {}
    timestamp: Optional[str] = None


class AnalyzeRequest(BaseModel):
    """Request for incident analysis"""
    alert: AlertRequest
    tenant_id: str
    api_key: str


class AnalyzeResponse(BaseModel):
    """Structured analysis response"""
    incident_id: str
    root_cause: str
    confidence_score: float
    remediation_steps: List[str]
    affected_services: List[str]
    severity: str
    analysis_time_ms: int
    similar_incidents_used: int


@app.on_event("startup")
async def startup_event():
    """Initialize models and services on Vercel cold start"""
    global reasoning_engine, tenant_manager, rag_system
    
    print("Starting up Incident IQ service...")
    
    # Initialize multi-tenant manager
    tenant_manager = TenantManager()
    
    # Register demo tenants
    tenant_manager.register_tenant("demo_corp", "Demo Corporation", "enterprise")
    tenant_manager.register_tenant("test_inc", "Test Inc", "pro")
    
    # Initialize RAG system
    rag_system = TenantAwareRAG(tenant_manager)
    
    # Initialize Nemotron reasoning engine
    # On Vercel free tier, use smaller model or disable heavy loading
    use_nemotron = os.getenv("USE_NEMOTRON", "false").lower() == "true"
    
    if use_nemotron:
        try:
            reasoning_engine = NemotronReasoningEngine(
                base_model_id="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
                adapter_path=os.getenv("LORA_ADAPTER_PATH"),
                use_4bit=True
            )
            print("Nemotron engine loaded successfully")
        except Exception as e:
            print(f"Failed to load Nemotron: {e}")
            reasoning_engine = None
    else:
        print("Running in lightweight mode (Nemotron disabled for free tier)")
        reasoning_engine = None


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Incident IQ",
        "version": "1.0.0",
        "status": "operational",
        "nemotron_available": reasoning_engine is not None,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "nemotron_loaded": reasoning_engine is not None,
        "tenant_count": len(tenant_manager.tenants) if tenant_manager else 0,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_incident(request: AnalyzeRequest):
    """
    Analyze an incident using the Nemotron reasoning model.
    
    Validates tenant via API key, ensures data isolation, and returns
    structured root cause analysis.
    """
    import time
    
    # 1. Validate tenant access
    if not tenant_manager:
        raise HTTPException(status_code=503, detail="Service initializing")
    
    tenant_id = tenant_manager.validate_request(request.api_key)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    if tenant_id != request.tenant_id:
        raise HTTPException(status_code=403, detail="API key does not match tenant")
    
    # 2. Prepare alert data
    alert_data = {
        "service": request.alert.service,
        "error": request.alert.error,
        "logs": request.alert.logs,
        "metrics": request.alert.metrics or {},
        "timestamp": request.alert.timestamp or datetime.now().isoformat()
    }
    
    # 3. Retrieve similar incidents from SAME tenant only
    similar_incidents = []
    if rag_system:
        similar_incidents = rag_system.find_similar_incidents(
            tenant_id, 
            alert_data, 
            top_k=3
        )
    
    context = ""
    if similar_incidents:
        context = "\n".join([
            f"Past incident {i+1}: {inc.get('root_cause', 'Unknown')}"
            for i, inc in enumerate(similar_incidents)
        ])
    
    # 4. Analyze with Nemotron (or fallback)
    start_time = time.time()
    
    if reasoning_engine:
        # Use actual Nemotron reasoning
        analysis = reasoning_engine.analyze_incident(alert_data, tenant_id, context)
        root_cause = analysis.root_cause
        confidence = analysis.confidence_score
        remediation = analysis.remediation_steps
        affected = analysis.affected_services
        severity = analysis.severity
    else:
        # Fallback rule-based analysis (for free tier testing)
        root_cause, confidence, remediation, affected, severity = _fallback_analysis(alert_data)
    
    analysis_time_ms = int((time.time() - start_time) * 1000)
    
    # 5. Store incident in tenant-isolated storage
    incident_data = {
        "alert": alert_data,
        "root_cause": root_cause,
        "confidence": confidence,
        "remediation": remediation,
        "severity": severity
    }
    
    incident_id = tenant_manager.store_incident(tenant_id, incident_data)
    
    # 6. Add to RAG index for future similarity matching
    if rag_system:
        rag_system.add_incident_to_index(tenant_id, incident_data)
    
    # 7. Update token usage for billing
    tenant_manager.tenants[tenant_id].total_tokens += 500  # Approximate
    
    return AnalyzeResponse(
        incident_id=incident_id,
        root_cause=root_cause,
        confidence_score=confidence,
        remediation_steps=remediation,
        affected_services=affected,
        severity=severity,
        analysis_time_ms=analysis_time_ms,
        similar_incidents_used=len(similar_incidents)
    )


@app.get("/api/tenant/usage")
async def get_tenant_usage(tenant_id: str, api_key: str):
    """Get usage report for billing (FinOps)"""
    if not tenant_manager:
        raise HTTPException(status_code=503, detail="Service initializing")
    
    validated_tenant = tenant_manager.validate_request(api_key)
    if not validated_tenant or validated_tenant != tenant_id:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    report = tenant_manager.get_usage_report(tenant_id)
    return report


@app.get("/api/tenant/incidents")
async def get_tenant_incidents(tenant_id: str, api_key: str, limit: int = 50):
    """Get incident history for this tenant only"""
    if not tenant_manager:
        raise HTTPException(status_code=503, detail="Service initializing")
    
    validated_tenant = tenant_manager.validate_request(api_key)
    if not validated_tenant or validated_tenant != tenant_id:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    incidents = tenant_manager.get_tenant_incidents(tenant_id, limit)
    return {"tenant_id": tenant_id, "incidents": incidents, "count": len(incidents)}


def _fallback_analysis(alert_data: Dict) -> tuple:
    """Rule-based fallback when Nemotron is not available"""
    logs = alert_data.get('logs', '').lower()
    error = alert_data.get('error', '').lower()
    
    # Simple pattern matching
    if 'database' in logs or 'connection pool' in logs:
        return (
            "Database connection pool exhaustion detected. Active connections exceeded configured maximum.",
            0.85,
            ["Increase connection pool size", "Add connection timeout", "Review long-running queries"],
            ["database"],
            "high"
        )
    elif 'api' in logs or 'gateway' in logs:
        return (
            "API gateway timeout. Backend service response time exceeded threshold.",
            0.75,
            ["Check backend service health", "Increase timeout settings", "Add retry logic"],
            ["api-gateway", "backend-service"],
            "medium"
        )
    elif 'memory' in logs or 'oom' in logs:
        return (
            "Out of memory error detected. Application exceeded allocated memory limit.",
            0.90,
            ["Increase memory allocation", "Review memory leak patterns", "Add memory monitoring"],
            ["application-server"],
            "critical"
        )
    else:
        return (
            "Unable to determine root cause automatically. Manual investigation required.",
            0.40,
            ["Check full logs", "Review recent deployments", "Check dependency health"],
            ["unknown"],
            "medium"
        )


# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
