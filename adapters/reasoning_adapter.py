"""
Simplified reasoning adapter that doesn't require torch.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass

@dataclass
class IncidentAnalysis:
    root_cause: str
    confidence_score: float
    remediation_steps: List[str]
    affected_services: List[str]
    severity: str

class NemotronReasoningEngine:
    def __init__(self, base_model_id: str = "", adapter_path: Optional[str] = None, use_4bit: bool = True):
        print("Nemotron Engine Ready (Demo Mode)")
    
    def analyze_incident(self, alert_data: Dict, tenant_id: str, context: str = None) -> IncidentAnalysis:
        logs = alert_data.get('logs', '').lower()
        
        if 'database' in logs or 'pool' in logs:
            return IncidentAnalysis(
                root_cause="Database connection pool exhaustion",
                confidence_score=0.85,
                remediation_steps=["Increase max_connections", "Add timeout"],
                affected_services=[alert_data.get('service', 'unknown')],
                severity="high"
            )
        elif 'memory' in logs or 'oom' in logs:
            return IncidentAnalysis(
                root_cause="Out of memory error",
                confidence_score=0.90,
                remediation_steps=["Increase memory limit", "Check for leaks"],
                affected_services=[alert_data.get('service', 'unknown')],
                severity="critical"
            )
        else:
            return IncidentAnalysis(
                root_cause="Unknown cause",
                confidence_score=0.40,
                remediation_steps=["Check logs", "Review changes"],
                affected_services=[alert_data.get('service', 'unknown')],
                severity="medium"
            )
