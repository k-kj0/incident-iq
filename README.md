# ⚡ Incident IQ + GTM Account Resolution

**Live dashboard (v1 incident analyzer):** https://incident-iq-drab.vercel.app/dashboard
**Repo:** https://github.com/k-kj0/incident-iq

This repo holds two things on one FastAPI codebase:

1. **GTM account resolution (new, `/api/v3/gtm`)**: merges the same company from many reps' sheets and tools into one account, then tells a rep who to call today and why.
2. **Incident IQ (original, `/api/analyze` and `/api/v2`)**: a multi-tenant root-cause analyzer for error logs.

---

## Part 1: GTM account resolution

### The problem

In many sales teams every rep runs their own setup. The same company sits in five private sheets under different names ("Acme GmbH", "ACME", "acme.de"), two reps call the same account in the same week, and nobody can say which account to call today.

This service fixes that one thing:

- **One account per real company.** Records from any source are normalized and merged into a single account.
- **Lineage.** Every raw record is kept, with the source it came from and how it was matched.
- **"Call today, and why."** Accounts are ranked by an explainable score, and every point has a sentence attached.
- **No double outreach.** If two reps have touched the same account, it is flagged `coordinate` instead of `call_today`.

### What it does

| Capability | How |
|---|---|
| Normalize messy input | URLs and emails reduce to a registrable domain; legal suffixes (GmbH, Ltd, Inc) and accents are stripped; free-mail and social profile domains are never used as keys |
| Resolve to one account | Same domain merges first; otherwise fuzzy name match inside the same country with no conflicting domain |
| Precision first | Short names (Stripe vs Stripes) and near-misses are **not merged**; they go to a human review queue |
| Idempotent ingest | A record is identified by `(tenant, source, source_record_id)`, so a failed batch can be re-sent safely |
| Dead letters | Rows that can't be loaded are saved with the reason instead of vanishing |
| Explainable scoring | Signals, market, company size and recency each add or subtract a stated number of points |
| Multi-tenant | Header auth with constant-time key comparison; every query is scoped to the tenant |

### Endpoints

All requests need the headers `X-Tenant-Id` and `X-Api-Key`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v3/gtm/ingest` | POST | Load a batch (up to 500 records) from one source |
| `/api/v3/gtm/call-list` | GET | Ranked accounts with reasons. `?recommendation=call_today` (default), `coordinate`, `wait` or `nurture`, plus `?limit=` |
| `/api/v3/gtm/accounts/{id}` | GET | One account with every source record that fed it |
| `/api/v3/gtm/duplicates` | GET | Near-matches waiting for human review |
| `/api/v3/gtm/dead-letters` | GET | Rejected rows with the reason |

### Scoring

| Rule | Points |
|---|---|
| A customer asked them for a security certification | +30 |
| Hiring for a security or compliance role | +25 |
| Mentions SOC 2 / ISO 27001 publicly | +20 |
| Raised funding recently | +15 |
| No public trust center | +10 |
| Based in a core European market | +15 |
| 20–500 employees | +15 |
| Never contacted | +5 |
| No contact for 30+ days | +5 |
| Touched in the last 7 days | −25 |

Recommendation: `coordinate` if two or more reps have touched the account, `wait` if touched in the last 7 days, `call_today` if the score is 50 or more, otherwise `nurture`. Unknown signals are stored but score nothing. The weights are my assumptions for a compliance-software sales team, not data from any real company.

### Measured result

Duplicate detection was checked against a hand-labeled fixture of 21 records covering 9 true company pairs, including typos, accents, `&` vs `and`, www and email-only domains, same names in different countries, and look-alike names.

| Metric | Result |
|---|---|
| Precision | **1.00** (no wrong merges) |
| Recall | **0.89** (8 of 9 true pairs found) |

The one miss is "International Business Machines" vs "IBM Corp", which no name-based method can know. It is left in the fixture on purpose. Run the check yourself with `python -m pytest tests/test_gtm_resolver.py -s`.

### Run it yourself (4 prompts)

These work in GitHub Codespaces or any machine with Python 3.12+ and Docker. Run them from the repo root.

**Prompt 1: install and run the tests (no database needed)**

```bash
pip install -r requirements.txt pytest
python -m pytest tests/test_gtm_resolver.py tests/test_gtm_api.py -q
```

Expect `15 passed`. The API tests use an in-memory SQLite database.

**Prompt 2: start Postgres and the API**

```bash
docker compose up -d db redis
export DATABASE_URL=postgresql://incident:incident@localhost:5432/incident
export REDIS_URL=redis://localhost:6379/0
PYTHONPATH=. python -m alembic upgrade head
PYTHONPATH=. python -m uvicorn api.app:app --port 8000
```

Leave this running and open a second terminal. No Docker? Create a free Postgres on Neon and set `DATABASE_URL` to its connection string instead.

**Prompt 3: load messy data from two reps**

```bash
H='-H X-Tenant-Id:demo_corp -H X-Api-Key:demo-key-123 -H Content-Type:application/json'
D45=$(date -u -d '45 days ago' +%FT%TZ); D40=$(date -u -d '40 days ago' +%FT%TZ)

curl -s -X POST localhost:8000/api/v3/gtm/ingest $H -d '{"source":"anna_sheet","records":[
 {"source_record_id":"1","company_name":"Acme GmbH","website":"https://www.acme.de","country":"DE","employee_count":120,"owner":"anna","signals":["hiring_security_role"],"last_touch_at":"'$D45'"},
 {"source_record_id":"2","company_name":"Orbit Security","website":"orbitsec.com","country":"FR","employee_count":80,"signals":["hiring_security_role","recent_funding"]},
 {"source_record_id":"3","company_name":"Stripe","website":"stripe.com","country":"US","employee_count":4000}]}' | python -m json.tool

curl -s -X POST localhost:8000/api/v3/gtm/ingest $H -d '{"source":"raj_hubspot","records":[
 {"source_record_id":"991","company_name":"ACME","contact_email":"cto@acme.de","owner":"raj","signals":["customer_asked_for_certification"],"last_touch_at":"'$D40'"},
 {"source_record_id":"992","company_name":"Helio Labs","website":"heliolabs.io","country":"Netherlands","employee_count":60,"signals":["customer_asked_for_certification"]},
 {"source_record_id":"993","company_name":"Stripes","website":"stripes.com","country":"US"},
 {"source_record_id":"994","company_name":"---"}]}' | python -m json.tool
```

Expected: the first batch creates 3 accounts. The second merges 1 (ACME into Acme GmbH by domain), creates 2, flags 1 for review (Stripes) and rejects 1 (`---`).

**Prompt 4: ask the system what to do**

```bash
H='-H X-Tenant-Id:demo_corp -H X-Api-Key:demo-key-123'
curl -s "localhost:8000/api/v3/gtm/call-list" $H | python -m json.tool
curl -s "localhost:8000/api/v3/gtm/call-list?recommendation=coordinate" $H | python -m json.tool
curl -s "localhost:8000/api/v3/gtm/accounts/1" $H | python -m json.tool
curl -s "localhost:8000/api/v3/gtm/duplicates" $H | python -m json.tool
curl -s "localhost:8000/api/v3/gtm/dead-letters" $H | python -m json.tool
```

Expected:

- **Call list:** Orbit Security (75) first, then Helio Labs (65), each with its reasons.
- **Coordinate list:** Acme GmbH (90), with the reason "2 reps have touched this account (anna, raj): agree who calls before anyone does".
- **Account detail:** both source records, `anna_sheet` and `raj_hubspot`, under Acme.
- **Duplicates:** Stripes, with Stripe as the possible match.
- **Dead letters:** the `---` row and why it was rejected.

### How it's built

```
POST /ingest
   │  for each record
   ▼
normalize (domain, name, country)
   │
   ▼
resolve ── same domain? ─────────────► merge into that account
   │        similar name, same country,
   │        no conflicting domain? ───► merge by name
   │        close but risky? ─────────► new account + flagged for review
   ▼
merge fields (owners, signals, latest touch) ── keep raw record with its source
   │
   ▼
GET /call-list  → score on read (so "days since last touch" is always current)
```

| File | Role |
|---|---|
| `backend/gtm/normalize.py` | Pure functions that turn messy values into comparable keys |
| `backend/gtm/resolver.py` | Pure entity resolution, easy to test with no database |
| `backend/gtm/scoring.py` | Pure scoring with an explanation for every point |
| `backend/gtm/service.py` | Batch ingest: resolve, merge, keep lineage, dead-letter bad rows |
| `backend/gtm/router.py` | FastAPI routes and tenant auth |
| `backend/gtm/models.py` | `gtm_accounts`, `gtm_raw_records`, `gtm_dead_letters` |
| `migrations/versions/0002_gtm.py` | Alembic migration for the three tables |

### Deploying the GTM API

The GTM routes need Postgres. On Vercel, set these environment variables, then redeploy:

| Variable | Value |
|---|---|
| `DATABASE_URL` | A Postgres connection string (for example a Neon pooled string) |
| `TENANT_KEYS` | JSON of tenant to key, for example `{"my_tenant":"a-long-random-key"}` |

Run `PYTHONPATH=. python -m alembic upgrade head` once against that database to create the tables. Without a database, the app still starts and serves the v1 dashboard, and the GTM routes are not usable. Use your own `TENANT_KEYS` in any deployment: the `demo-key-123` style keys below are public.

### Limits (stated honestly)

- **Scale.** Each batch loads a tenant's accounts into memory to match against. That is fine for thousands of accounts; beyond that, add a `pg_trgm` index.
- **Late links.** If two existing accounts later turn out to be the same company, they are not auto-merged; they surface for review.
- **Removing signals.** Re-ingesting a record can add or update signals but not remove them.
- **Scoring is rule-based.** The weights are assumptions, so tune them against real won and lost deals before trusting them.
- **No external data sources yet.** Signals arrive with the records. Pulling them from public sources (job boards, funding news) is the next step.
- **Scoring on read.** It is recomputed on every read for freshness, which is simple but linear in account count.

---

## Part 2: Incident IQ (original project)

**Live demo:** https://incident-iq-drab.vercel.app/dashboard
**API base:** https://incident-iq-drab.vercel.app

### What is this?

Incident IQ is a small multi-tenant API + dashboard that takes raw error logs and returns a likely root cause, a confidence score, and concrete remediation steps, instead of just telling you *that* something broke, like most monitoring tools do.

You paste in a service name, an error message, and a log excerpt. It matches the log content against a set of known incident patterns (database exhaustion, OOM, CPU spikes, API gateway failures, disk/network issues) and returns a structured response with a reasoning trace showing *why* it reached that conclusion.

### How it actually works

This is a **rule-based pattern-matching engine**, not a hosted ML model. It was originally built as a submission for an NVIDIA Nemotron hackathon challenge, with a LoRA fine-tuning script included in the repo (`train_lora.py`), but the live, deployed API does **not** call that model. The deployed version runs entirely on deterministic keyword/pattern matching (see `IncidentReasoningEngine` in `api/app.py`), which is fast, has zero inference cost, and is honest about its limits.

The `reasoning_trace` field in every API response shows the exact matching logic that fired, so the "reasoning" is inspectable rather than a black box.

### Two runtimes, one codebase

| Runtime | Entry | Storage | Use |
|---|---|---|---|
| Vercel serverless | `api/app.py` via Mangum | in-memory per tenant, resets on cold start (v1); Postgres when `DATABASE_URL` is set (v2, v3) | public demo |
| Docker / Kubernetes | `uvicorn api.app:app` | Postgres 16 + pgvector, Redis | v2 and v3 APIs |

See `docs/ARCHITECTURE.md` for the v2 request flow, failure modes, observability and the Kubernetes runbook.

### Live endpoints (v1)

| Endpoint | Method | Description |
|---|---|---|
| `/dashboard` | GET | Visual UI |
| `/health` | GET | Health check |
| `/api/analyze` | POST | Submit an incident for analysis |
| `/api/tenant/incidents` | GET | Fetch incident history for a tenant |

### Example request

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

### Demo credentials

These are public demo keys for the dashboard only. Never reuse them for real data.

| Tenant | API Key |
|---|---|
| `demo_corp` | `demo-key-123` |
| `test_inc` | `test-key-456` |

### Multi-tenancy

Each tenant has its own API key and isolated incident history. There's no cross-tenant data access: a request with `test_inc`'s tenant ID and `demo_corp`'s API key is rejected.

**Storage note:** in the v1 Vercel build, incident history is held in memory and resets on every cold start or redeploy. The v2 routes store incidents in Postgres with pgvector similarity search.

### Detected incident patterns

| Pattern | Confidence | Severity |
|---|---|---|
| Database connection pool exhaustion | 85% | High |
| Out of memory / heap exhaustion | 90% | Critical |
| Service timeout / high latency | 75% | Medium |
| API gateway / 502 errors | 70% | High |
| Disk space exhaustion | 80% | High |
| Network connectivity failure | 75% | High |
| CPU overload / throttling | 70% | Medium |
| Unmatched, flagged for manual review | 40% | Medium |

---

## Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy, Alembic
- **Data:** PostgreSQL (pgvector for v2 similarity search), Redis (optional cache)
- **Logging and quality:** structlog JSON logs, pytest, GitHub Actions CI
- **Deployment:** Vercel (serverless via Mangum), Docker, Kubernetes manifests in `k8s/`
- **Frontend:** vanilla HTML/CSS/JS, no framework

## Project structure

```
incident-iq/
├── api/
│   └── app.py                  # FastAPI app, v1 routes, dashboard and reasoning engine
├── backend/
│   ├── core.py                 # settings, DB, cache, logging shared by v2 and v3
│   ├── router.py               # /api/v2 incident routes
│   └── gtm/                    # /api/v3/gtm account resolution (normalize, resolver, scoring, service, router, models)
├── migrations/versions/        # 0001 incidents, 0002 GTM tables
├── tests/                      # test_v2.py, test_gtm_resolver.py, test_gtm_api.py
├── eval/ and scripts/          # labeled incident set and benchmark script
├── k8s/ and docs/              # Kubernetes manifests, ARCHITECTURE.md
├── data/synthetic_generator.py # synthetic data for the LoRA experiment
├── train_lora.py               # LoRA script (Colab), not called by the live API
├── requirements.txt
├── vercel.json
└── README.md
```

**Why is the dashboard HTML embedded in `app.py`?** It was originally a separate static file, but Vercel's Python bundler did not reliably package sibling files from `api/`, which caused runtime crashes. One self-contained file deploys reliably.

## Deployment

Auto-deploys to Vercel on every push to `main`.

## License

MIT, free to use, modify, and build on.

---

Built by [k-kj0](https://github.com/k-kj0).
