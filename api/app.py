from dataclasses import dataclass
from typing import List

@dataclass
class IncidentAnalysis:
    root_cause: str
    confidence_score: float
    remediation_steps: List[str]
    affected_services: List[str]
    severity: str
    reasoning_trace: List[str]


class NemotronReasoningEngine:

    def analyze_incident(self, logs: str, service: str):

        trace = []

        if "database" in logs.lower():
            trace.append("Found database keyword")
            trace.append("Matched connection pool pattern")

            return IncidentAnalysis(
                root_cause="Database connection pool exhaustion",
                confidence_score=0.85,
                remediation_steps=[
                    "Increase max connections",
                    "Review connection leaks",
                    "Add timeout limits"
                ],
                affected_services=[service],
                severity="high",
                reasoning_trace=trace
            )

        if "memory" in logs.lower():
            trace.append("Found memory keyword")
            trace.append("Matched OOM pattern")

            return IncidentAnalysis(
                root_cause="Out of memory error",
                confidence_score=0.90,
                remediation_steps=[
                    "Increase memory limit",
                    "Profile memory usage",
                    "Restart service"
                ],
                affected_services=[service],
                severity="critical",
                reasoning_trace=trace
            )

        trace.append("No known pattern matched")

        return IncidentAnalysis(
            root_cause="Unknown issue",
            confidence_score=0.40,
            remediation_steps=["Inspect logs manually"],
            affected_services=[service],
            severity="medium",
            reasoning_trace=trace
        )
