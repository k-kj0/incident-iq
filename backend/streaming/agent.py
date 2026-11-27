"""LangGraph briefing agent.

Flow:  retrieve similar past incidents -> explain (LangChain + Gemini) -> verify
       -> END, or -> fallback (deterministic template) when verification fails.

The LLM only writes the wording. The root cause, severity and fixes come from the
existing rule engine, and verify() rejects any summary that drops the root cause
or cites an incident id that retrieval did not return.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Optional, TypedDict

import structlog
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from .config import GEMINI_MODEL

log = structlog.get_logger()

# retriever(tenant_id, embedding, k) -> [{"incident_id", "service", "root_cause", "similarity"}]
Retriever = Callable[[str, Optional[list], int], list]


class AgentState(TypedDict, total=False):
    tenant_id: str
    alert: dict
    analysis: dict
    embedding: Optional[list]
    similar: list
    summary: str
    summary_source: str  # "llm" or "template"
    grounded: bool


PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an SRE assistant. Write a briefing of at most 3 sentences using ONLY the "
     "facts given. Name the root cause exactly as written. Mention a past incident only "
     "by an id from the list. Do not invent services, numbers or fixes."),
    ("human",
     "Service: {service}\nError: {error}\nRoot cause: {root_cause}\n"
     "Confidence: {confidence}\nSeverity: {severity}\nSuggested fixes: {fixes}\n"
     "Similar past incidents:\n{similar}"),
])


def template_summary(alert: dict, analysis: dict, similar: list) -> str:
    fixes = analysis.get("remediation_steps") or []
    text = (
        f"{alert.get('service', 'service')}: {analysis.get('root_cause', 'unknown')} "
        f"(confidence {analysis.get('confidence_score', 0):.2f}, "
        f"severity {analysis.get('severity', 'unknown')})."
    )
    if fixes:
        text += f" First fix to try: {fixes[0]}."
    if similar:
        ids = ", ".join(s["incident_id"] for s in similar)
        text += f" Similar past incidents: {ids}."
    return text


def is_grounded(summary: str, analysis: dict, similar: list) -> bool:
    if not summary.strip():
        return False
    if analysis.get("root_cause", "").lower() not in summary.lower():
        return False
    known = {s["incident_id"] for s in similar}
    cited = set(re.findall(r"\binc-\w+", summary))
    return cited <= known


def build_llm():
    """Return a LangChain chat model, or None when no key is set (template mode)."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL, google_api_key=key, temperature=0, timeout=20, max_retries=1
        )
    except Exception as exc:
        log.warning("llm_init_failed", error=str(exc))
        return None


def build_agent(retriever: Retriever, llm=None):
    chain = (PROMPT | llm | StrOutputParser()) if llm is not None else None

    def retrieve(state: AgentState) -> dict:
        try:
            similar = retriever(state["tenant_id"], state.get("embedding"), 3)
        except Exception as exc:  # retrieval is optional context, never fatal
            log.warning("retrieval_failed", error=str(exc))
            similar = []
        return {"similar": similar}

    def explain(state: AgentState) -> dict:
        alert, analysis, similar = state["alert"], state["analysis"], state["similar"]
        if chain is None:
            return {"summary": "", "summary_source": "template"}
        try:
            text = chain.invoke({
                "service": alert["service"],
                "error": alert["error"],
                "root_cause": analysis["root_cause"],
                "confidence": analysis["confidence_score"],
                "severity": analysis["severity"],
                "fixes": "; ".join(analysis.get("remediation_steps") or []) or "none",
                "similar": "\n".join(
                    f"- {s['incident_id']} ({s['service']}): {s['root_cause']}" for s in similar
                ) or "none",
            })
            return {"summary": text.strip(), "summary_source": "llm"}
        except Exception as exc:
            log.warning("llm_call_failed", error=str(exc))
            return {"summary": "", "summary_source": "template"}

    def verify(state: AgentState) -> dict:
        if state["summary_source"] != "llm":
            return {"grounded": False}
        return {"grounded": is_grounded(state["summary"], state["analysis"], state["similar"])}

    def route(state: AgentState) -> str:
        return "ok" if state["grounded"] else "fallback"

    def fallback(state: AgentState) -> dict:
        return {
            "summary": template_summary(state["alert"], state["analysis"], state["similar"]),
            "summary_source": "template",
        }

    g = StateGraph(AgentState)
    g.add_node("retrieve", retrieve)
    g.add_node("explain", explain)
    g.add_node("verify", verify)
    g.add_node("fallback", fallback)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "explain")
    g.add_edge("explain", "verify")
    g.add_conditional_edges("verify", route, {"ok": END, "fallback": "fallback"})
    g.add_edge("fallback", END)
    return g.compile()
