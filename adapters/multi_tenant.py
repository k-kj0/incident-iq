from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json


@dataclass
class TenantContext:
    """Isolated context for each customer"""
    tenant_id: str
    name: str
    plan: str  # free, pro, enterprise
    api_keys: List[str] = field(default_factory=list)
    request_count: int = 0
    total_tokens: int = 0
    
    
class TenantManager:
    """
    Multi-tenant manager ensuring complete data isolation between customers.
    
    This follows the pattern used by SaaS platforms like Incident IQ where
    each customer sees ONLY their own data, even in shared dashboards [citation:2][citation:7].
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
        
        return api_key
    
    def validate_request(self, api_key: str) -> Optional[str]:
        """Validate API key and return tenant_id if valid"""
        for tenant_id, context in self.tenants.items():
            if api_key in context.api_keys:
                # Update usage metrics
                context.request_count += 1
                return tenant_id
        return None
    
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
            "estimated_cost_usd": context.total_tokens * 0.000001,  # $0.001 per 1k tokens
            "period_start": datetime.now().replace(day=1).isoformat(),
            "period_end": datetime.now().isoformat()
        }


class TenantAwareRAG:
    """
    RAG system that respects tenant boundaries.
    Similar incidents are only retrieved from the same tenant's history.
    """
    
    def __init__(self, tenant_manager: TenantManager):
        self.tenant_manager = tenant_manager
        # In production, use proper vector DB per tenant
        self.tenant_vectors: Dict[str, List] = {}
    
    def add_incident_to_index(self, tenant_id: str, incident: Dict):
        """Add incident to tenant-specific vector store"""
        if tenant_id not in self.tenant_vectors:
            self.tenant_vectors[tenant_id] = []
        
        # Store with tenant isolation
        self.tenant_vectors[tenant_id].append({
            "embedding": self._simple_hash_embedding(incident.get("root_cause", "")),
            "data": incident
        })
    
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
        
        current_hash = self._simple_hash_embedding(
            current_incident.get("error", "") + current_incident.get("logs", "")
        )
        
        # Search only within this tenant's vectors
        candidates = []
        for stored in self.tenant_vectors[tenant_id]:
            similarity = self._cosine_similarity(
                current_hash, 
                stored["embedding"]
            )
            candidates.append((similarity, stored["data"]))
        
        # Sort by similarity and return top_k
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in candidates[:top_k]]
    
    def _simple_hash_embedding(self, text: str) -> List[float]:
        """Simplified embedding - in production use proper embeddings"""
        import hashlib
        hash_obj = hashlib.md5(text.encode())
        hash_bytes = hash_obj.digest()
        return [float(b) / 255.0 for b in hash_bytes[:32]]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        return dot / (norm_a * norm_b + 1e-8)
