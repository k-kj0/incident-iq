# ⚡ Incident IQ — Root Cause Analysis for System Incidents

**Live demo:** https://incident-iq-drab.vercel.app/dashboard
**API base:** https://incident-iq-drab.vercel.app
**Repo:** https://github.com/k-kj0/incident-iq

## What is this?

Incident IQ is a small multi-tenant API + dashboard that takes raw error logs and returns a likely root cause, a confidence score, and concrete remediation steps — instead of just telling you *that* something broke, like most monitoring tools do.

You paste in a service name, an error message, and a log excerpt. It matches the log content against a set of known incident patterns (database exhaustion, OOM, CPU spikes, API gateway failures, disk/network issues) and returns a structured response with a reasoning trace showing *why* it reached that conclusion.

## How it actually works

This is a **rule-based pattern-matching engine**, not a hosted ML model. It was originally built as a submission for an NVIDIA Nemotron hackathon challenge, with a LoRA fine-tuning script included in the repo (`train_lora.py`) — but the live, deployed API does **not** call that model. The deployed version runs entirely on deterministic keyword/pattern matching (see `IncidentReasoningEngine` in `api/app.py`), which is fast, has zero inference cost, and is honest about its limits.

The `reasoning_trace` field in every API response shows the exact matching logic that fired, so the "reasoning" is inspectable rather than a black box.

## Live endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/dashboard` | GET | Visual UI |
| `/health` | GET | Health check |
| `/api/analyze` | POST | Submit an incident for analysis |
| `/api/tenant/incidents` | GET | Fetch incident history for a tenant |

## Example request

```bash
curl -X POST https://incident-iq-drab.vercel.app/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "alert": {
      "service": "payment-api",
      "error": "Connection timeout",
      "logs": "ERROR: database connection pool exhausted. Active connections: 50/50.",
      "metrics": {"latency_ms": 5000}
    },
    "tenant_id": "demo_corp",
    "api_key": "demo-key-123"
  }'
```

Response:

```json
{
  "incident_id": "inc-1748123456",
  "root_cause": "Database connection pool exhaustion",
  "confidence_score": 0.85,
  "remediation_steps": [
    "Increase max_connections in database config",
    "Add connection timeout and retry logic",
    "Review code for connection leaks",
    "Implement connection pooling monitoring"
  ],
  "reasoning_trace": [
    "Found database/connection-pool keyword",
    "Matched connection pool exhaustion pattern"
  ],
  "affected_services": ["payment-api"],
  "severity": "high",
  "analysis_time_ms": 45,
  "tenant": "demo_corp"
}
```

## Demo credentials

| Tenant | API Key |
|---|---|
| `demo_corp` | `demo-key-123` |
| `test_inc` | `test-key-456` |

## Multi-tenancy

Each tenant has its own API key and isolated incident history. There's no cross-tenant data access — a request with `test_inc`'s tenant ID and `demo_corp`'s API key is rejected.

**Storage note:** incident history is held in-memory and resets on every cold start / redeploy. This is fine for a demo; a production version would back this with Postgres or Redis.

## Detected incident patterns

| Pattern | Confidence | Severity |
|---|---|---|
| Database connection pool exhaustion | 85% | High |
| Out of memory / heap exhaustion | 90% | Critical |
| Service timeout / high latency | 75% | Medium |
| API gateway / 502 errors | 70% | High |
| Disk space exhaustion | 80% | High |
| Network connectivity failure | 75% | High |
| CPU overload / throttling | 70% | Medium |
| Unmatched — flagged for manual review | 40% | Medium |

## Tech stack

- **Backend:** Python, FastAPI
- **Deployment:** Vercel (serverless), via Mangum (ASGI → Lambda adapter)
- **Frontend:** Vanilla HTML/CSS/JS, no framework

## Project structure

```
incident-iq/
├── api/
│   └── app.py              # FastAPI app, routes, and reasoning engine (single file — see note below)
├── data/
│   └── synthetic_generator.py   # Synthetic training data generator, used for the LoRA experiment
├── train_lora.py           # LoRA fine-tuning script (Google Colab), not called by the live API
├── requirements.txt
├── vercel.json
└── README.md
```

**Why is the frontend HTML embedded in `app.py` instead of a separate static file?** It was originally split out, but Vercel's Python serverless bundler didn't reliably package sibling files/modules from the `api/` directory, which caused runtime crashes. Keeping it as a single self-contained file avoids that packaging issue. Not the prettiest structure, but it's the one that reliably deploys.

## Local development

```bash
pip install -r requirements.txt
uvicorn api.app:app --host 0.0.0.0 --port 8000
```

## Deployment

Auto-deploys to Vercel on every push to `main`.

```bash
vercel --prod
```

## License

MIT — free to use, modify, and build on.

---

Built by [k-kj0](https://github.com/k-kj0).
