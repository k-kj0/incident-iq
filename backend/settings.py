import json
import os

_raw = os.getenv("DATABASE_URL", "")
# Neon/Render give postgresql://...; SQLAlchemy needs the psycopg driver name.
DATABASE_URL = _raw.replace("postgresql://", "postgresql+psycopg://", 1)

REDIS_URL = os.getenv("REDIS_URL", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
EMBED_DIM = 768

# Same demo tenants as the README. Override with TENANT_KEYS='{"acme":"secret"}'.
TENANT_KEYS = json.loads(
    os.getenv("TENANT_KEYS", '{"demo_corp":"demo-key-123","test_inc":"test-key-456"}')
)
