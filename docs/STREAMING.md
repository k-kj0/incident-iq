# Streaming ingestion (Kafka) and LangGraph briefings

Alerts can arrive on a Kafka topic instead of (or as well as) `POST /api/v2/analyze`.

```
producers -> incident.alerts -> consumer -> rule engine (root cause, severity, fixes)
                                   |-> pgvector: similar past incidents (same tenant only)
                                   |-> LangGraph: retrieve -> explain (Gemini) -> verify
                                   |-> incident.results (result + briefing)
                                   |-> Postgres incidents table (same table the REST API uses)
             failures after 3 tries, or malformed messages -> incident.alerts.dlq
```

## Message format (JSON on `incident.alerts`)

```json
{"alert_id": "a1b2c3d4e5", "tenant_id": "demo_corp", "service": "payments-api",
 "error": "pool exhausted", "logs": "max connections reached"}
```

## Run it

```bash
docker compose up -d --build                  # db, redis, api, kafka, consumer
pip install confluent-kafka
python scripts/produce_alerts.py --count 20 --bad   # --bad adds one malformed message
docker compose logs -f consumer
curl "localhost:8000/api/v2/incidents?tenant_id=demo_corp&api_key=demo-key-123&limit=5"
python scripts/kafka_lag.py                   # consumer-group lag per partition
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic incident.alerts.dlq --from-beginning --timeout-ms 5000
```

Set `GEMINI_API_KEY` for LLM-written briefings and embeddings. Without it, the consumer
still works: briefings use a template and similar-incident retrieval returns nothing.

## Design decisions

- **At-least-once delivery.** Offsets are committed only after a message is processed,
  skipped as a duplicate, or written to the dead-letter topic. If the DLQ write fails the
  consumer exits without committing and the restarted container reprocesses the message.
- **Idempotent writes.** `incident_id` is derived from `alert_id`, so a replay is skipped.
  The result is published before the Postgres save, so a crash between the two can send
  the result twice; downstream consumers should dedupe on `incident_id`.
- **Poison messages are not retried.** Bad JSON, missing fields and unknown tenants go
  straight to the DLQ. Other failures retry with backoff (0.5 s, 1 s) up to 3 attempts.
- **Ordering.** The producer keys by service, so one service's alerts stay in order.
- **The LLM only writes wording.** Root cause, severity and fixes come from the rule
  engine. The verify step rejects a briefing that drops the root cause or cites an incident
  id retrieval did not return, and the graph falls back to a template.
- **Tenant isolation.** Retrieval filters by tenant, and unknown tenants are dead-lettered.

## Tests

`pytest tests/test_streaming.py` runs without a broker or database (17 tests: grounding
check, fallback paths, retry and backoff, DLQ routing, duplicate skip).

## Not covered by tests

The real Kafka loop (`main()` in `consumer.py`), `store.py` against Postgres, and the
Gemini call. Verify them with the docker compose steps above.
