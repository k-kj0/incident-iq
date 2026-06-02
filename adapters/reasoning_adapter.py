import torch
import sys
from typing import Dict, Any, Optional, List
from transformers import (
    AutoModelForCausalLM, 
    AutoTokenizer, 
    BitsAndBytesConfig
)
from peft import PeftModel
from pydantic import BaseModel


class IncidentAnalysis(BaseModel):
    """Structured output for incident analysis"""
    root_cause: str
    confidence_score: float
    remediation_steps: List[str]
    affected_services: List[str]
    severity: str  # critical, high, medium, low


class NemotronReasoningEngine:
    """
    Loads LoRA-adapted Nemotron model with proper cache handling
    for the hybrid Mamba-Attention architecture [citation:4][citation:6].
    """
    
    def __init__(
        self, 
        base_model_id: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
        adapter_path: Optional[str] = None,
        use_4bit: bool = True
    ):
        self.base_model_id = base_model_id
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        print(f"Loading base model on {self.device}...")
        
        # Setup quantization for memory efficiency
        bnb_config = None
        if use_4bit and torch.cuda.is_available():
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4"
            )
        
        # Load base model
        self.base_model = AutoModelForCausalLM.from_pretrained(
            base_model_id,
            device_map="auto" if torch.cuda.is_available() else None,
            quantization_config=bnb_config,
            torch_dtype=torch.bfloat16,
            trust_remote_code=True
        )
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(base_model_id)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        # Load LoRA adapter if provided
        if adapter_path:
            print(f"Loading LoRA adapter from {adapter_path}...")
            self.model = PeftModel.from_pretrained(self.base_model, adapter_path)
        else:
            self.model = self.base_model
        
        self.model.eval()
        
        # Initialize Mamba-specific cache
        self._init_mamba_cache()
        
    def _init_mamba_cache(self):
        """Initialize the specialized cache for Mamba-Attention hybrid [citation:4]"""
        try:
            # Get the hybrid cache class from the model module
            model_module = sys.modules[self.base_model.__class__.__module__]
            HybridCache = getattr(model_module, 'HybridMambaAttentionDynamicCache')
            
            self.past_key_values = HybridCache(
                self.base_model.config, 
                batch_size=1, 
                dtype=torch.bfloat16, 
                device=self.model.device
            )
        except (AttributeError, KeyError):
            # Fallback for non-Mamba environments
            self.past_key_values = None
            print("Warning: Mamba cache not available, using standard attention")
    
    def analyze_incident(
        self, 
        alert_data: Dict[str, Any],
        tenant_id: str,
        context: Optional[str] = None
    ) -> IncidentAnalysis:
        """
        Analyze an incident using the fine-tuned reasoning model.
        
        Args:
            alert_data: Dictionary containing log lines, metrics, and alert details
            tenant_id: Customer identifier for multi-tenant isolation
            context: Additional context from RAG (past similar incidents)
        """
        
        # Build prompt with structured format for deterministic output
        prompt = self._build_reasoning_prompt(alert_data, context)
        
        # Format with chat template
        messages = [{"role": "user", "content": prompt}]
        formatted_prompt = self.tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )
        
        # Tokenize
        inputs = self.tokenizer(
            formatted_prompt, 
            return_tensors="pt"
        ).to(self.model.device)
        
        # Generate with appropriate parameters [citation:4]
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.1,  # Low temp for deterministic reasoning
                top_p=0.95,
                do_sample=False,  # Deterministic for production
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                past_key_values=self.past_key_values
            )
        
        # Decode response
        response = self.tokenizer.decode(
            outputs[0][inputs['input_ids'].shape[1]:], 
            skip_special_tokens=True
        )
        
        # Parse response into structured format
        analysis = self._parse_response(response)
        
        # Add tenant metadata for isolation [citation:2]
        analysis.affected_services = self._identify_affected_services(alert_data)
        analysis.severity = self._classify_severity(alert_data)
        
        return analysis
    
    def _build_reasoning_prompt(self, alert_data: Dict, context: str = None) -> str:
        """Build a structured prompt that forces step-by-step reasoning"""
        
        prompt = f"""Analyze this system incident and provide root cause analysis.

ALERT DETAILS:
- Service: {alert_data.get('service', 'unknown')}
- Error: {alert_data.get('error', 'unknown')}
- Timestamp: {alert_data.get('timestamp', 'N/A')}
- Metrics: {alert_data.get('metrics', {})}

LOG EXCERPTS:
{alert_data.get('logs', 'No logs provided')}

"""
        
        if context:
            prompt += f"SIMILAR PAST INCIDENTS:\n{context}\n\n"
        
        prompt += """Follow this reasoning structure:

STEP 1: Identify the primary symptom
STEP 2: Analyze possible causes based on logs
STEP 3: Eliminate impossible causes
STEP 4: Determine root cause with confidence score
STEP 5: Propose remediation steps

Respond in JSON format:
{
    "root_cause": "string description",
    "confidence_score": 0.0-1.0,
    "remediation_steps": ["step1", "step2"],
    "analysis_trace": ["reasoning step 1", "step 2"]
}

Root cause analysis:"""
        
        return prompt
    
    def _parse_response(self, response: str) -> IncidentAnalysis:
        """Parse model response into structured IncidentAnalysis"""
        import json
        import re
        
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return IncidentAnalysis(
                    root_cause=data.get('root_cause', 'Unknown'),
                    confidence_score=data.get('confidence_score', 0.5),
                    remediation_steps=data.get('remediation_steps', ['Check logs', 'Restart service']),
                    affected_services=['unknown'],
                    severity='medium'
                )
            except json.JSONDecodeError:
                pass
        
        # Fallback: extract from text
        return IncidentAnalysis(
            root_cause=response[:200],
            confidence_score=0.5,
            remediation_steps=['Investigate manually'],
            affected_services=['unknown'],
            severity='medium'
        )
    
    def _identify_affected_services(self, alert_data: Dict) -> List[str]:
        """Extract service names from alert data"""
        services = set()
        
        if 'service' in alert_data:
            services.add(alert_data['service'])
        
        # Parse logs for service mentions
        logs = alert_data.get('logs', '')
        # Simple extraction - in production use proper parsing
        if 'database' in logs.lower():
            services.add('database')
        if 'api' in logs.lower() or 'gateway' in logs.lower():
            services.add('api-gateway')
        
        return list(services) if services else ['unknown']
    
    def _classify_severity(self, alert_data: Dict) -> str:
        """Classify severity based on alert content"""
        logs = alert_data.get('logs', '').lower()
        error = alert_data.get('error', '').lower()
        
        critical_keywords = ['critical', 'outage', 'down', 'security', 'breach']
        high_keywords = ['error', 'failed', 'timeout', '500', 'exception']
        
        for kw in critical_keywords:
            if kw in logs or kw in error:
                return 'critical'
        
        for kw in high_keywords:
            if kw in logs or kw in error:
                return 'high'
        
        return 'medium'
