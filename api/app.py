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


@app.post("/api/analyze", response_model=Analy
