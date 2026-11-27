"""Print consumer-group lag per partition (messages produced but not yet committed).

  python scripts/kafka_lag.py
Lag that keeps growing means the consumer is slower than the producers or is stuck.
"""
import os

from confluent_kafka import Consumer, TopicPartition

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC = os.getenv("KAFKA_TOPIC_ALERTS", "incident.alerts")
GROUP = os.getenv("KAFKA_GROUP_ID", "incident-iq-analyzer")


def main() -> None:
    c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": GROUP, "enable.auto.commit": False})
    meta = c.list_topics(TOPIC, timeout=10).topics[TOPIC]
    if meta.error:
        raise SystemExit(f"topic {TOPIC} not found: {meta.error}")
    parts = [TopicPartition(TOPIC, p) for p in meta.partitions]
    committed = {tp.partition: tp.offset for tp in c.committed(parts, timeout=10)}
    total = 0
    for p in sorted(meta.partitions):
        low, high = c.get_watermark_offsets(TopicPartition(TOPIC, p), timeout=10)
        done = committed.get(p, -1001)  # -1001 means nothing committed yet
        lag = high - (low if done < 0 else done)
        total += lag
        print(f"partition {p}: end={high} committed={'none' if done < 0 else done} lag={lag}")
    print(f"total lag: {total}")
    c.close()


if __name__ == "__main__":
    main()
