<<<<<<< HEAD
from typing import Dict, Optional, List
=======
cat > adapters/multi_tenant.py << 'EOF'
"""
Multi-tenant management with complete data isolation between customers.
No external dependencies required.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
>>>>>>> 7500a8f56d3ad0eda1afccb1d01e648c1ee265fd
from datetime import datetime
import hashlib

class TenantManager:
<<<<<<< HEAD
    def __init__(self):
        self.tenants = {}
    
    def register_tenant(self, tenant_id: str, name: str, plan: str = "pro") -> str:
        api_key = hashlib.md5(f"{tenant_id}{datetime.now()}".encode()).hexdigest()[:16]
        self.tenants[tenant_id] = {"name": name, "api_keys": [api_key], "incidents": []}
=======
    """
    Multi-tenant manager ensuring complete data isolation between customers.
    
    Each tenant has:
    - Unique API keys for authentication
    - Isolated incident storage (no cross-tenant access)
    - Separate usage metrics for billing
    """
    
    def __init__(self):
        self.tenants: Dict[str, TenantContext] = {}
        self.tenant_data: Dict[str, Dict] = {}  # Isolated data stores
        
    def register_tenant(
        self, 
        tenant_id: str, 
        name: str, 
        plan: str = "pro"
    ) -> str:
        """Register a new customer/tenant"""
        
        # Generate API key for this tenant
        api_key = hashlib.sha256(
            f"{tenant_id}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:32]
        
        self.tenants[tenant_id] = TenantContext(
            tenant_id=tenant_id,
            name=name,
           plan=plan,
            api_keys=[api_key]
        )
        
        # Initialize isolated data store
        self.tenant_data[tenant_id] = {
            "alerts": [],
            "incidents": [],
            "analyses": []
        }
        
>>>>>>> 7500a8f56d3ad0eda1afccb1d01e648c1ee265fd
        return api_key
    
    def validate_request(self, api_key: str) -> Optional[str]:
        for tid, data in self.tenants.items():
            if api_key in data["api_keys"]:
                return tid
        return None
    
<<<<<<< HEAD
    def store_incident(self, tenant_id: str, incident: Dict) -> str:
        inc_id = hashlib.md5(f"{tenant_id}{datetime.now()}".encode()).hexdigest()[:8]
        self.tenants[tenant_id]["incidents"].append({"id": inc_id, "data": incident})
        return inc_id
    
    def get_tenant_incidents(self, tenant_id: str, limit: int = 100) -> List:
        return self.tenants.get(tenant_id, {}).get("incidents", [])[-limit:]
=======
    def store_incident(
        self, 
        tenant_id: str, 
        incident_data: Dict[str, Any]
    ) -> str:
        """
        Store incident data in tenant-isolated storage.
        No other tenant can access this data.
        """
        if tenant_id not in self.tenant_data:
            raise ValueError(f"Tenant {tenant_id} not found")
        
        incident_id = hashlib.md5(
            json.dumps(incident_data, sort_keys=True).encode()
        ).hexdigest()[:12]
        
        incident_record = {
            "incident_id": incident_id,
            "timestamp": datetime.now().isoformat(),
            "data": incident_data
        }
        
        self.tenant_data[tenant_id]["incidents"].append(incident_record)
        
        # Keep only last 500 incidents per tenant
        if len(self.tenant_data[tenant_id]["incidents"]) > 500:
            self.tenant_data[tenant_id]["incidents"] = self.tenant_data[tenant_id]["incidents"][-500:]
        
        return incident_id
    
    def get_tenant_incidents(
        self, 
        tenant_id: str, 
        limit: int = 100
    ) -> List[Dict]:
        """
        Retrieve ONLY this tenant's incidents.
        Filtering happens at the storage layer to prevent cross-tenant leakage.
        """
        if tenant_id not in self.tenant_data:
            return []
        
        incidents = self.tenant_data[tenant_id]["incidents"][-limit:]
        return incidents
    
    def get_usage_report(self, tenant_id: str) -> Dict:
        """Generate cost/usage report for billing (FinOps)"""
        if tenant_id not in self.tenants:
            return {}
        
        context = self.tenants[tenant_id]
        return {
            "tenant_id": tenant_id,
            "tenant_name": context.name,
            "plan": context.plan,
            "total_requests": context.request_count,
            "total_tokens": context.total_tokens,
            "estimated_cost_usd": round(context.total_tokens * 0.000001, 4),
            "period_start": datetime.now().replace(day=1).isoformat(),
            "period_end": datetime.now().isoformat()
        }

>>>>>>> 7500a8f56d3ad0eda1afccb1d01e648c1ee265fd

class TenantAwareRAG:
    def __init__(self, manager):
        self.manager = manager
        self.index = {}
    
    def add_incident_to_index(self, tenant_id: str, incident: Dict):
<<<<<<< HEAD
        if tenant_id not in self.index:
            self.index[tenant_id] = []
        self.index[tenant_id].append(incident)
    
    def find_similar_incidents(self, tenant_id: str, current: Dict, top_k: int = 3) -> List:
        return self.index.get(tenant_id, [])[-top_k:]
=======
        """Add incident to tenant-specific vector store"""
        if tenant_id not in self.tenant_vectors:
            self.tenant_vectors[tenant_id] = []
        
        # Create simple keyword-based index
        keywords = self._extract_keywords(incident.get("data", {}).get("alert", {}).get("logs", ""))
        
        self.tenant_vectors[tenant_id].append({
            "keywords": keywords,
            "data": incident,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last 200
        if len(self.tenant_vectors[tenant_id]) > 200:
            self.tenant_vectors[tenant_id] = self.tenant_vectors[tenant_id][-200:]
    
    def find_similar_incidents(
        self, 
        tenant_id: str, 
        current_incident: Dict, 
        top_k: int = 3
    ) -> List[Dict]:
        """
        Find similar incidents from the SAME tenant only.
        Cross-tenant retrieval is BLOCKED by design.
        """
        if tenant_id not in self.tenant_vectors:
            return []
        
        current_logs = current_incident.get("logs", "").lower()
        current_keywords = self._extract_keywords(current_logs)
        
        # Search only within this tenant's vectors
        candidates = []
        for stored in self.tenant_vectors[tenant_id]:
            # Simple keyword overlap scoring
            overlap = len(set(current_keywords) & set(stored["keywords"]))
            if overlap > 0:
                candidates.append((overlap, stored["data"]))
        
        # Sort by overlap and return top_k
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in candidates[:top_k]]
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract simple keywords from text"""
        # Common error keywords
        keywords = set()
        error_keywords = ["database", "timeout", "memory", "cpu", "disk", "network", 
                         "connection", "api", "gateway", "error", "failed", "crash"]
        
        text_lower = text.lower()
        for kw in error_keywords:
            if kw in text_lower:
                keywords.add(kw)
        
        return list(keywords)
EOF
>>>>>>> 7500a8f56d3ad0eda1afccb1d01e648c1ee265fd
