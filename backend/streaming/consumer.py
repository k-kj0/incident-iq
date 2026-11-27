"""Kafka consumer: incident.alerts -> analyze -> LangGraph briefing -> Postgres + incident.results.

Delivery is at-least-once. Offsets are committed only after a message is fully handled
(processed, skipped as a duplicate, or written to the dead-letter topic). Incident ids
come from the alert id, so a replayed message is skipped instead of saved twice.
Run:  python -m backend.streaming.consumer
"""
from __future__ import annotations

import json
import re
import signal
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import structlog

from ..settings import TENANT_KEYS
from .config import (BOOTSTRAP, GROUP_ID, MAX_ATTEMPTS, PARTITIONS, REPLICATION,
                     TOPIC_ALERTS, TOPIC_DLQ, TOPIC_RESULTS)

log = structlog.get_logger()
REQUIRED = ("alert_id", "tenant_id", "service", "error")


class BadMessage(Exception):
    """Malformed or unauthorised message. Retrying cannot fix it, so it is not retried."""


@dataclass
class Deps:
    analyze: Callable[[dict], dict]
    embed: Callable[[str], Optional[list]]
    agent: Any  # compiled LangGraph graph
    exists: Callable[[str], bool]
    save: Callable[[str, str, dict, dict, Optional[list]], None]
    publish: Callable[[str, str, bytes, dict], None]  # topic, key, value, headers


def parse(raw: bytes) -> dict:
    try:
        msg = json.loads(raw)
    except ValueError as exc:  # includes bad UTF-8 and bad JSON
        raise BadMessage(f"not valid JSON: {exc}") from exc
    if not isinstance(msg, dict):
        raise BadMessage("message must be a JSON object")
    missing = [f for f in REQUIRED if not msg.get(f)]
    if missing:
        raise BadMessage(f"missing fields: {', '.join(missing)}")
    if msg["tenant_id"] not in TENANT_KEYS:
        raise BadMessage(f"unknown tenant: {msg['tenant_id']}")
    return msg


def incident_id_for(alert_id: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]", "", str(alert_id))[:32]
    if not clean:
        raise BadMessage("alert_id has no usable characters")
    return f"inc-{clean}"


def process(raw: bytes, deps: Deps) -> str:
    msg = parse(raw)
    incident_id = incident_id_for(msg["alert_id"])
    if deps.exists(incident_id):
        return "skipped"

    alert = {"service": msg["service"], "error": msg["error"],
             "logs": msg.get("logs", ""), "metrics": msg.get("metrics", {})}
    result = deps.analyze(alert)
    result["incident_id"] = incident_id

    vec = deps.embed(f"{alert['service']}\n{alert['error']}\n{alert['logs']}")
    state = deps.agent.invoke({
        "tenant_id": msg["tenant_id"], "alert": alert, "analysis": result, "embedding": vec,
    })
    result["briefing"] = {
        "summary": state["summary"],
        "source": state["summary_source"],  # "llm" or "template"
        "similar_incident_ids": [s["incident_id"] for s in state["similar"]],
    }

    # Publish first, then save: a crash in between replays the message and sends the
    # result twice, which consumers dedupe on incident_id. Save-first could lose it.
    deps.publish(TOPIC_RESULTS, incident_id, json.dumps(result).encode(),
                 {"tenant_id": msg["tenant_id"]})
    deps.save(incident_id, msg["tenant_id"], alert, result, vec)
    return "processed"


def handle(raw: bytes, key: Optional[bytes], deps: Deps,
           sleep: Callable[[float], None] = time.sleep,
           max_attempts: int = MAX_ATTEMPTS) -> str:
    """Process with retries and backoff; dead-letter anything that cannot succeed."""
    last: Exception = RuntimeError("no attempts")
    for attempt in range(1, max_attempts + 1):
        try:
            return process(raw, deps)
        except BadMessage as exc:
            return _dead_letter(raw, key, deps, exc, attempt)
        except Exception as exc:
            last = exc
            log.warning("attempt_failed", attempt=attempt, error=str(exc))
            if attempt < max_attempts:
                sleep(0.5 * 2 ** (attempt - 1))
    return _dead_letter(raw, key, deps, last, max_attempts)


def _dead_letter(raw: bytes, key: Optional[bytes], deps: Deps, exc: Exception, attempts: int) -> str:
    deps.publish(TOPIC_DLQ, (key or b"").decode(errors="replace"), raw,
                 {"error": str(exc)[:500], "attempts": str(attempts)})
    log.error("dead_lettered", error=str(exc), attempts=attempts)
    return "dead_lettered"


def ensure_topics() -> None:
    """Create the three topics if they do not exist yet (safe to run on every start)."""
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    futures = admin.create_topics([
        NewTopic(t, num_partitions=PARTITIONS, replication_factor=REPLICATION)
        for t in (TOPIC_ALERTS, TOPIC_RESULTS, TOPIC_DLQ)
    ])
    for topic, future in futures.items():
        try:
            future.result()
        except Exception as exc:
            if "TOPIC_ALREADY_EXISTS" not in str(exc):
                log.warning("topic_create_failed", topic=topic, error=str(exc))


def main() -> None:
    from confluent_kafka import Consumer, Producer

    from api.app import _analyze_for_v2  # the existing rule engine
    from ..core import embed
    from . import store
    from .agent import build_agent, build_llm

    deps_agent = build_agent(store.similar, build_llm())
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "enable.idempotence": True})

    def publish(topic: str, key: str, value: bytes, headers: dict) -> None:
        errors: list = []
        producer.produce(topic, key=key, value=value, headers=headers,
                         on_delivery=lambda err, _m: errors.append(err) if err else None)
        producer.flush(10)
        if errors:
            raise RuntimeError(f"publish to {topic} failed: {errors[0]}")

    deps = Deps(analyze=_analyze_for_v2, embed=embed, agent=deps_agent,
                exists=store.exists, save=store.save, publish=publish)

    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    })
    ensure_topics()
    consumer.subscribe([TOPIC_ALERTS])

    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("consumer_started", topic=TOPIC_ALERTS, group=GROUP_ID, bootstrap=BOOTSTRAP)

    try:
        while running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                log.warning("kafka_error", error=str(msg.error()))
                continue
            t0 = time.perf_counter()
            outcome = handle(msg.value() or b"", msg.key(), deps)
            # If handle() raises (e.g. the DLQ is unreachable) we exit WITHOUT committing,
            # and the restarted container reprocesses this message.
            consumer.commit(message=msg, asynchronous=False)
            log.info("message_done", outcome=outcome, partition=msg.partition(),
                     offset=msg.offset(), ms=round((time.perf_counter() - t0) * 1000, 1))
    finally:
        consumer.close()
        log.info("consumer_stopped")


if __name__ == "__main__":
    from ..logging_conf import configure_logging

    configure_logging()
    main()
