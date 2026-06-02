from typing import Dict, Optional, List
from datetime import datetime
import hashlib

class TenantManager:
    def __init__(self):
        self.tenants = {}
    
    def register_tenant(self, tenant_id: str, name: str, plan: str = "pro") -> str:
        api_key = hashlib.md5(f"{tenant_id}{datetime.now()}".encode()).hexdigest()[:16]
        self.tenants[tenant_id] = {"name": name, "api_keys": [api_key], "incidents": []}
        return api_key
    
    def validate_request(self, api_key: str) -> Optional[str]:
        for tid, data in self.tenants.items():
            if api_key in data["api_keys"]:
                return tid
        return None
    
    def store_incident(self, tenant_id: str, incident: Dict) -> str:
        inc_id = hashlib.md5(f"{tenant_id}{datetime.now()}".encode()).hexdigest()[:8]
        self.tenants[tenant_id]["incidents"].append({"id": inc_id, "data": incident})
        return inc_id
    
    def get_tenant_incidents(self, tenant_id: str, limit: int = 100) -> List:
        return self.tenants.get(tenant_id, {}).get("incidents", [])[-limit:]

class TenantAwareRAG:
    def __init__(self, manager):
        self.manager = manager
        self.index = {}
    
    def add_incident_to_index(self, tenant_id: str, incident: Dict):
        if tenant_id not in self.index:
            self.index[tenant_id] = []
        self.index[tenant_id].append(incident)
    
    def find_similar_incidents(self, tenant_id: str, current: Dict, top_k: int = 3) -> List:
        return self.index.get(tenant_id, [])[-top_k:]
