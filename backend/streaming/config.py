import os

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_ALERTS = os.getenv("KAFKA_TOPIC_ALERTS", "incident.alerts")
TOPIC_RESULTS = os.getenv("KAFKA_TOPIC_RESULTS", "incident.results")
TOPIC_DLQ = os.getenv("KAFKA_TOPIC_DLQ", "incident.alerts.dlq")
GROUP_ID = os.getenv("KAFKA_GROUP_ID", "incident-iq-analyzer")
MAX_ATTEMPTS = int(os.getenv("KAFKA_MAX_ATTEMPTS", "3"))

# Chat model used by the LangChain explain step. Change it if Google retires the name.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Used only when the consumer creates missing topics at startup (dev default: 1 broker).
PARTITIONS = int(os.getenv("KAFKA_PARTITIONS", "3"))
REPLICATION = int(os.getenv("KAFKA_REPLICATION", "1"))
