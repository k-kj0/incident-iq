"""No Kafka broker and no database needed: every dependency is injected."""
import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from backend.streaming.agent import build_agent, build_llm, is_grounded
from backend.streaming.config import TOPIC_DLQ, TOPIC_RESULTS
from backend.streaming.consumer import (BadMessage, Deps, handle, incident_id_for,
                                        parse, process)

ANALYSIS = {"root_cause": "Database connection pool exhaustion", "confidence_score": 0.88,
            "severity": "high", "remediation_steps": ["Increase max_connections"]}
ALERT = {"service": "payments-api", "error": "pool exhausted", "logs": "max connections"}
SIMILAR = [{"incident_id": "inc-abc123", "service": "payments-api",
            "root_cause": "Database connection pool exhaustion", "similarity": 0.91}]


def run_agent(llm, similar=SIMILAR):
    agent = build_agent(lambda tenant, vec, k: similar, llm)
    return agent.invoke({"tenant_id": "demo_corp", "alert": ALERT,
                         "analysis": dict(ANALYSIS), "embedding": [0.1]})


def test_llm_summary_used_when_grounded():
    out = run_agent(FakeListChatModel(responses=[
        "Database connection pool exhaustion on payments-api. Seen before in inc-abc123."]))
    assert out["summary_source"] == "llm"
    assert "inc-abc123" in out["summary"]


def test_invented_incident_id_falls_back_to_template():
    out = run_agent(FakeListChatModel(responses=[
        "Database connection pool exhaustion. Same as inc-zzz999."]))
    assert out["summary_source"] == "template"
    assert "inc-zzz999" not in out["summary"]


def test_summary_missing_root_cause_falls_back():
    out = run_agent(FakeListChatModel(responses=["Something unrelated happened."]))
    assert out["summary_source"] == "template"
    assert "Database connection pool exhaustion" in out["summary"]


def test_no_llm_uses_template():
    out = run_agent(None)
    assert out["summary_source"] == "template"
    assert "Increase max_connections" in out["summary"]


def test_retrieval_failure_is_not_fatal():
    def boom(*_):
        raise RuntimeError("db down")
    agent = build_agent(boom, None)
    out = agent.invoke({"tenant_id": "demo_corp", "alert": ALERT,
                        "analysis": dict(ANALYSIS), "embedding": None})
    assert out["similar"] == []


def test_is_grounded_rules():
    assert is_grounded("Database connection pool exhaustion.", ANALYSIS, [])
    assert not is_grounded("", ANALYSIS, [])


def test_build_llm_none_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert build_llm() is None


# ---------- consumer ----------
def msg(**over):
    base = {"alert_id": "a1b2c3", "tenant_id": "demo_corp", "service": "payments-api",
            "error": "pool exhausted", "logs": "max connections reached"}
    base.update(over)
    return json.dumps(base).encode()


class Recorder:
    def __init__(self, exists=False, fail_times=0):
        self.published, self.saved = [], []
        self._exists, self.fail_times, self.calls = exists, fail_times, 0

    def deps(self):
        def analyze(alert):
            self.calls += 1
            if self.calls <= self.fail_times:
                raise ConnectionError("transient")
            return dict(ANALYSIS)
        return Deps(
            analyze=analyze, embed=lambda t: [0.1],
            agent=build_agent(lambda tenant, vec, k: [], None),
            exists=lambda i: self._exists,
            save=lambda *a: self.saved.append(a),
            publish=lambda topic, key, value, headers: self.published.append(
                (topic, key, value, headers)),
        )


def test_process_publishes_then_saves():
    r = Recorder()
    assert process(msg(), r.deps()) == "processed"
    assert r.published[0][0] == TOPIC_RESULTS
    body = json.loads(r.published[0][2])
    assert body["incident_id"] == "inc-a1b2c3"
    assert body["briefing"]["source"] == "template"
    assert r.saved[0][0] == "inc-a1b2c3"


def test_duplicate_alert_is_skipped():
    r = Recorder(exists=True)
    assert process(msg(), r.deps()) == "skipped"
    assert r.published == [] and r.saved == []


@pytest.mark.parametrize("raw", [b"not json", b"[]", msg(tenant_id="nobody"),
                                 json.dumps({"alert_id": "x"}).encode()])
def test_bad_messages_rejected(raw):
    with pytest.raises(BadMessage):
        parse(raw)


def test_poison_message_goes_straight_to_dlq_without_retry():
    r = Recorder()
    sleeps = []
    assert handle(b"not json", b"k", r.deps(), sleep=sleeps.append) == "dead_lettered"
    assert r.published[0][0] == TOPIC_DLQ
    assert r.published[0][3]["attempts"] == "1"
    assert sleeps == [] and r.calls == 0


def test_transient_failure_is_retried_then_succeeds():
    r = Recorder(fail_times=2)
    sleeps = []
    assert handle(msg(), b"k", r.deps(), sleep=sleeps.append, max_attempts=3) == "processed"
    assert sleeps == [0.5, 1.0]


def test_persistent_failure_dead_letters_after_max_attempts():
    r = Recorder(fail_times=99)
    out = handle(msg(), b"k", r.deps(), sleep=lambda s: None, max_attempts=3)
    assert out == "dead_lettered"
    assert r.published[-1][0] == TOPIC_DLQ
    assert r.published[-1][3]["attempts"] == "3"
    assert r.saved == []


def test_incident_id_is_deterministic_and_clean():
    assert incident_id_for("a1-b2_c3!") == "inc-a1b2c3"
    with pytest.raises(BadMessage):
        incident_id_for("---")
