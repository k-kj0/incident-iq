cat > adapters/reasoning_adapter.py << 'EOF'
"""
Simplified reasoning adapter that doesn't require torch.
For the hackathon demo, this simulates Nemotron's reasoning.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class IncidentAnalysis:
    """Structured output for incident analysis"""
    root_cause: str
    confidence_score: float
    remediation_steps: List[str]
    affected_services: List[str]
    severity: str  # critical, high, medium, low


class NemotronReasoningEngine:
    """
    Simulated Nemotron reasoning engine for demo.
    In production, this would load the actual model.
    """
    
    def __init__(
        self, 
        base_model_id: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
        adapter_path: Optional[str] = None,
        use_4bit: bool = True
    ):
        print(f"Initializing Nemotron Reasoning Engine (Demo Mode)")
        print(f"Base model: {base_model_id}")
        if adapter_path:
            print(f"Would load LoRA adapter from: {adapter_path}")
        print("Running in simulation mode - no GPU required")
    
    def analyze_incident(
        self, 
        alert_data: Dict[str, Any],
        tenant_id: str,
        context: Optional[str] = None
    ) -> IncidentAnalysis:
        """
        Analyze an incident using simulated reasoning.
        This follows the same structure as the real Nemotron would.
        """
        
        logs = alert_data.get('logs', '').lower()
        error = alert_data.get('error', '').lower()
        service = alert_data.get('service', 'unknown')
        
        # Step-by-step reasoning (simulates chain-of-thought)
        reasoning_steps = []
        
        # Step 1: Identify primary symptom
        reasoning_steps.append(f"Analyzing incident for tenant: {tenant_id}")
        reasoning_steps.append(f"Service affected: {service}")
        
        if 'error' in alert_data:
            reasoning_steps.append(f"Error message: {alert_data['error']}")
        
        # Step 2: Pattern matching
        if 'database' in logs or 'connection pool' in logs or 'postgres' in logs or 'mysql' in logs:
            reasoning_steps.append("Pattern match: Database connectivity issue detected")
            root_cause = "Database connection pool exhaustion. Active connections exceeded configured maximum."
            confidence = 0.85
            remediation_steps = [
                "Increase max_connections in database configuration",
                "Add connection timeout and retry logic to application",
                "Review code for connection leaks (missing connection.close())",
                "Implement connection pooling monitoring and alerts",
                "Consider read replicas for query distribution"
            ]
            affected_services = [service, "database"]
            severity = "high"
            
        elif 'memory' in logs or 'oom' in logs or 'out of memory' in logs:
            reasoning_steps.append("Pattern match: Memory exhaustion detected")
            root_cause = "Application memory leak or insufficient heap allocation"
            confidence = 0.90
            remediation_steps = [
                "Increase memory limit to 8GB or higher",
                "Run heap profiler (jmap, MAT) to identify leak source",
                "Add automatic restart on OOM with backoff",
                "Implement memory usage alerts at 80% and 90%",
                "Review code for unbounded cache or collection growth"
            ]
            affected_services = [service]
            severity = "critical"
            
        elif 'timeout' in logs or 'slow' in logs or 'latency' in logs:
            reasoning_steps.append("Pattern match: Performance degradation detected")
            root_cause = "Service timeout due to slow downstream responses or resource contention"
            confidence = 0.75
            remediation_steps = [
                "Add caching layer (Redis) for frequent queries",
                "Optimize slow database queries with proper indexes",
                "Increase timeout from 30s to 60s as temporary fix",
                "Implement circuit breaker pattern to prevent cascading failures",
                "Add request tracing to identify bottleneck"
            ]
            affected_services = [service, "downstream-services"]
            severity = "medium"
            
        elif 'api' in logs or 'gateway' in logs or 'nginx' in logs:
            reasoning_steps.append("Pattern match: API gateway error detected")
            root_cause = "API gateway configuration issue or upstream service failure"
            confidence = 0.70
            remediation_steps = [
                "Check upstream service health and availability",
                "Verify API gateway routing rules and rate limits",
                "Review authentication service status",
                "Check SSL certificates expiry",
                "Increase API gateway replicas for high availability"
            ]
            affected_services = [service, "api-gateway"]
            severity = "high"
            
        elif 'disk' in logs or 'storage' in logs or 'space' in logs:
            reasoning_steps.append("Pattern match: Storage issue detected")
            root_cause = "Disk space exhaustion or storage performance degradation"
            confidence = 0.80
            remediation_steps = [
                "Clean up old logs and temporary files",
                "Implement log rotation with compression",
                "Increase disk size or add more storage",
                "Move old data to cold storage (S3)",
                "Set up disk usage alerts at 70% and 85%"
            ]
            affected_services = [service, "storage"]
            severity = "high"
            
        elif 'network' in logs or 'connection refused' in logs or 'unreachable' in logs:
            reasoning_steps.append("Pattern match: Network connectivity issue detected")
            root_cause = "Network connectivity failure between services"
            confidence = 0.75
            remediation_steps = [
                "Check network security groups and firewall rules",
                "Verify DNS resolution and service discovery",
                "Test connectivity with telnet/nc from affected service",
                "Check load balancer health checks",
                "Review network latency and packet loss metrics"
            ]
            affected_services = [service, "network"]
            severity = "high"
            
        elif 'cpu' in logs or 'high load' in logs:
            reasoning_steps.append("Pattern match: CPU saturation detected")
            root_cause = "CPU resource exhaustion due to compute-intensive operations"
            confidence = 0.70
            remediation_steps = [
                "Profile application to identify CPU-intensive code paths",
                "Add horizontal scaling (more replicas)",
                "Move batch processing to background jobs",
                "Optimize algorithms and add caching",
                "Consider vertical scaling (larger instance type)"
            ]
            affected_services = [service]
            severity = "medium"
            
        else:
            reasoning_steps.append("No clear pattern match - performing deeper analysis")
            root_cause = "Unable to determine root cause automatically. Manual investigation required."
            confidence = 0.40
            remediation_steps = [
                "Collect full application and system logs from last hour",
                "Check all dependent services status",
                "Review recent code deployments and configuration changes",
                "Enable debug logging and attempt to reproduce",
                "Check metrics dashboards for anomalies",
                "Consider rolling back recent changes if applicable"
            ]
            affected_services = [service, "unknown"]
            severity = "medium"
        
        # Step 3: Incorporate context from similar incidents
        if context and context.strip():
            reasoning_steps.append(f"Context provided: {len(context)} chars of similar incidents")
            reasoning_steps.append("Cross-referencing with historical patterns")
            # Boost confidence if context matches
            if any(word in context.lower() for word in root_cause.lower().split()[:3]):
                confidence = min(0.95, confidence + 0.05)
                reasoning_steps.append("Pattern confirmed by historical incidents")
        
        # Step 4: Final confidence assessment
        confidence_level = "High" if confidence > 0.7 else "Medium" if confidence > 0.5 else "Low"
        reasoning_steps.append(f"Confidence score: {confidence:.2%} - {confidence_level} confidence in diagnosis")
        reasoning_steps.append(f"Recommended action: {remediation_steps[0] if remediation_steps else 'Investigate'}")
        
        # Store reasoning trace for debugging
        self.last_reasoning = reasoning_steps
        
        return IncidentAnalysis(
            root_cause=root_cause,
            confidence_score=confidence,
            remediation_steps=remediation_steps,
            affected_services=affected_services,
            severity=severity
        )
    
    def get_reasoning_trace(self) -> List[str]:
        """Get the reasoning trace from the last analysis"""
        return getattr(self, 'last_reasoning', [])
EOF
