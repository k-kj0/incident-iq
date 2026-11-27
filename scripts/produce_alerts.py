"""Send sample alerts to Kafka.

  python scripts/produce_alerts.py --count 20
  python scripts/produce_alerts.py --bad        # adds one malformed message to show the DLQ
"""
import argparse
import json
import os
import random
import time
import uuid

from confluent_kafka import Producer

SAMPLES = [
    ("payments-api", "pool exhausted", "database connection pool exhausted, max connections reached"),
    ("orders-api", "OutOfMemoryError", "java.lang.OutOfMemoryError: Java heap space"),
    ("search-api", "timeout", "request timed out after 30s, latency spike 4200 ms"),
    ("auth-service", "pool exhausted", "too many connections, pool exhausted"),
]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--rate", type=float, default=5, help="messages per second")
    p.add_argument("--tenant", default="demo_corp")
    p.add_argument("--bad", action="store_true", help="also send one malformed message")
    a = p.parse_args()

    topic = os.getenv("KAFKA_TOPIC_ALERTS", "incident.alerts")
    producer = Producer({"bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP", "localhost:9092"),
                         "enable.idempotence": True})

    for _ in range(a.count):
        service, error, logs = random.choice(SAMPLES)
        msg = {"alert_id": uuid.uuid4().hex[:10], "tenant_id": a.tenant,
               "service": service, "error": error, "logs": logs}
        # key = service keeps one service's alerts in order on a single partition
        producer.produce(topic, key=service, value=json.dumps(msg).encode())
        producer.poll(0)
        time.sleep(1 / a.rate)
    if a.bad:
        producer.produce(topic, key="bad", value=b"this is not json")
    producer.flush(10)
    print(f"sent {a.count} alerts{' + 1 malformed' if a.bad else ''} to {topic}")


if __name__ == "__main__":
    main()
