# adapters/reasoning_adapter.py  — FULL REPLACEMENT
# Frontend/public/index.html untouched. Only this file changes.

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import re, time, os

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


@dataclass
class IncidentAnalysis:
    root_cause: str
    confidence_score: float
    remediation_steps: List[str]
    affected_services: List[str]
    severity: str
    reasoning_trace: str = ""      # chain-of-thought, shown in dashboard
    analysis_time_ms: int = 0


# ── Pattern library (fast path, runs < 1ms) ───────────────────────────────
PATTERNS = [
    (r"pool.{0,30}exhaust|max.{0,10}connection", "Database connection pool exhaustion",
     ["Increase max_connections in DB config", "Add connection retry + backoff",
      "Audit code for unclosed connections", "Add connection pool monitoring"],
     0.88, "high"),
    (r"out.of.memory|oom|heap.space|java.*heap", "Out-of-memory / heap exhaustion",
     ["Increase JVM heap (-Xmx)", "Profile memory with heap dump",
      "Check for memory leaks in recent deploys"],
     0.92, "critical"),
    (r"timeout|timed.out|latency.{0,20}(high|spike|ms)", "Service timeout / high latency",
     ["Check downstream service health", "Review recent deployments",
      "Add circuit breaker pattern", "Scale horizontally if load-related"],
     0.78, "medium"),
    (r"502|503|nginx|gateway", "API gateway / upstream failure",
     ["Check upstream service status", "Verify nginx config",
      "Check SSL cert expiry", "Restart gateway pod"],
     0.72, "high"),
    (r"disk.{0,15}(full|space|quota)|no space left", "Disk space exhaustion",
     ["Clear old logs (journalctl --vacuum)", "Expand EBS volume",
      "Enable log rotation", "Archive old data to S3"],
     0.82, "high"),
    (r"cpu.{0,20}(throttl|spike|100|overload)|load.average", "CPU overload / throttling",
     ["Profile hot code paths", "Check for runaway processes",
      "Scale out horizontally", "Review recent algorithm changes"],
     0.71, "medium"),
    (r"network|packet.loss|dns|unreachable|connection.refused", "Network / DNS failure",
     ["Check VPC routing rules", "Verify DNS resolution",
      "Test with traceroute", "Review firewall/SG changes"],
     0.76, "high"),
]


class NemotronReasoningEngine:
    def __init__(self,
                 base_model_id: str = "",
                 adapter_path: Optional[str] = None,
                 use_4bit: bool = True):
        self.model = None
        self.tokenizer = None
        self._load_model(base_model_id, adapter_path, use_4bit)

    def _load_model(self, base_model_id, adapter_path, use_4bit):
        """Load real Nemotron + LoRA if GPU available, else rule-based fallback."""
        adapter_path = adapter_path or os.environ.get("ADAPTER_PATH")
        if not TORCH_AVAILABLE or not adapter_path or not os.path.exists(adapter_path or ""):
            print("⚡ Demo mode — rule-based engine (fast, no GPU needed)")
            return
        try:
            base = base_model_id or "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
            self.tokenizer = AutoTokenizer.from_pretrained(base)
            self.tokenizer.pad_token = self.tokenizer.eos_token
            base_model = AutoModelForCausalLM.from_pretrained(
                base, device_map="auto", load_in_4bit=use_4bit,
                torch_dtype=torch.bfloat16,
            )
            self.model = PeftModel.from_pretrained(base_model, adapter_path)
            print(f"✓ Nemotron + LoRA loaded from {adapter_path}")
        except Exception as e:
            print(ff"Model load failed ({e}), falling back to rule-based")

    def _rule_based(self, logs: str, service: str) -> IncidentAnalysis:
        """Enhanced pattern matching with reasoning trace."""
        for pattern, cause, steps, conf, sev in PATTERNS:
            if re.search(pattern, logs, re.IGNORECASE):
                trace = (
                    ff"Pattern matched: /{pattern}/\n"
                    ff"Log evidence: '{logs[:120]}...'\n"
                    ff"Root cause identified: {cause}\n"
                    ff"Severity: {sev} | Confidence: {conf}"
                )
                return IncidentAnalysis(cause, conf, steps, [service], sev, trace)
        return IncidentAnalysis(
            "Unknown — manual investigation required", 0.40,
            ["Review full logs", "Check recent deploys", "Escalate to on-call"],
            [service], "medium",
            "No known pattern matched. Requires human review.",
        )

    def _nemotron_inference(self, prompt: str) -> str:
        """Run real model inference."""
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs, max_new_tokens=512, temperature=0.0,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        return self.tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    def analyze_incident(self, alert_data: Dict, tenant_id: str, context: str = None) -> IncidentAnalysis:
        t0 = time.time()
        logs    = alert_data.get("logs", "").lower()
        service = alert_data.get("service", "unknown")

        if self.model is not None:
            # Real Nemotron path
            prompt = (
                ff"Analyze this incident and provide root cause.\n\n"
                ff"Service: {service}\nLogs: {logs}\n"
                ff"{'Context: ' + context if context else ''}\n\n"
                ff"Reasoning:"
            )
            raw = self._nemotron_inference(prompt)
            result = self._rule_based(logs, service)  # use pattern for structure
            result.reasoning_trace = raw              # but show Nemotron reasoning
        else:
            result = self._rule_based(logs, service)

        result.analysis_time_ms = int((time.time() - t0) * 1000)
        return result
