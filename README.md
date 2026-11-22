# Incident IQ + GTM + QuoteLens

One FastAPI + PostgreSQL codebase with three projects on it:

1. **QuoteLens (`/api/v3/quotes`)**: compares commercial insurance quotes and shows the exact source text behind every extracted number. Any value it cannot verify is flagged, not shown as fact.
2. **GTM account resolution (`/api/v3/gtm`)**: merges the same company from many reps' sheets into one account and ranks who to call today, with a reason.
3. **Incident IQ (`/api/analyze`, `/api/v2`)**: the original multi-tenant root-cause analyzer for error logs.

**Live dashboard (v1 incident analyzer):** https://incident-iq-drab.vercel.app/dashboard
**Repo:** https://github.com/k-kj0/incident-iq

---

## Part 1: QuoteLens

### The problem

Commercial insurance quotes are dense PDFs, and every carrier words things differently. One calls a cover "E&O", another "Professional Liability". Comparing quotes means re-keying numbers by hand and hoping none were misread. When AI does the extraction, the next problem is trust: a confident, wrong limit or deductible in a comparison table is worse than no table.

QuoteLens is a demo of one way to approach this:

- **Every value carries a citation** (page and character span) pointing at the text it came from.
- **A citation checker re-reads the document** and compares. It does not ask the model whether it is right, so an invented number is caught whichever extractor produced it.
- **Coverage labels are normalized**, so quotes can be put side by side.
- **Gaps are flagged**: a cover one carrier did not quote, a lower limit, an exclusion that only one quote has.

This is a portfolio demo built on synthetic sample quotes. It is not based on any company's real pipeline, documents or customer data.

### What it does

| Capability | How |
|---|---|
| Extract from PDFs | `pdfplumber` reads text-based PDFs; a rule-based extractor pulls carrier, premium, coverage limits and deductibles, and exclusions |
| Cite every value | Each value has `{page, start, end, text}` where `text == page_text[start:end]` |
| Verify citations | `verify.py` checks the page exists, the span is inside the page, the cited text matches the document, and the number matches the cited text |
| Normalize coverage names | Alias table plus a strict fuzzy match; short or unknown labels stay `unmapped` instead of being guessed |
| Compare quotes | Side-by-side rows per coverage with gap, lower-limit and exclusion-difference flags |
| Optional LLM extraction | Gemini returns each value with an exact snippet; claims whose snippet is not on the page, or whose number disagrees with its snippet, are rejected |
| Click-to-source demo page | `/api/v3/quotes/ui` shows the comparison; clicking a value highlights its source text |
| Multi-tenant | Same header auth as the rest of the repo; every query is scoped to the tenant |

### How the citation check works

```
page text ──► extractor (rules or LLM) ──► claims, each with a citation
                                                │
                                                ▼
                  verify: page exists? span inside page? cited text == document text?
                          does the number parse out of the cited text?
                                                │
                                ok ─► shown as verified
                                fail ─► shown as unverified (rules) or rejected (LLM path)
```

Tests show both failure modes: a value changed to a number the document does not contain, and a citation whose text or page does not exist.

### Endpoints

All requests except `/ui` need the headers `X-Tenant-Id` and `X-Api-Key`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v3/quotes` | POST | Ingest a quote as page text: `{"filename", "pages": [...], "extractor": "rules" or "llm"}` |
| `/api/v3/quotes/upload` | POST | Upload a text-based PDF (up to 10 MB) |
| `/api/v3/quotes` | GET | List this tenant's quotes |
| `/api/v3/quotes/{id}` | GET | One quote with its pages, extraction, verification results and rejected claims |
| `/api/v3/quotes/compare` | POST | Compare 2 to 5 quotes: `{"quote_ids": [1, 2]}` |
| `/api/v3/quotes/ui` | GET | Demo page: upload two PDFs, compare, click a value to see its source |

### Run it yourself

Works in GitHub Codespaces or any machine with Python 3.12+ and Docker. Run from the repo root.

**1. Install and run the tests (no database needed)**

```bash
pip install -r requirements.txt -r requirements-backend.txt reportlab
python -m pytest tests/test_quotes.py -q
```

Expect `11 passed`. The API tests use in-memory SQLite. Without `reportlab`, the PDF upload test is skipped.

**2. Start Postgres and the API**

```bash
docker compose up -d db redis
export DATABASE_URL=postgresql://incident:incident@localhost:5432/incident
export REDIS_URL=redis://localhost:6379/0
PYTHONPATH=. python -m alembic upgrade head
PYTHONPATH=. python -m uvicorn api.app:app --port 8000
```

Leave it running and open a second terminal. No Docker? Create a free Postgres on Neon, run `CREATE EXTENSION IF NOT EXISTS vector;` once, and set `DATABASE_URL` to its connection string.

**3. Ingest and compare two sample quotes**

```bash
H='-H X-Tenant-Id:demo_corp -H X-Api-Key:demo-key-123 -H Content-Type:application/json'
curl -s -X POST localhost:8000/api/v3/quotes $H -d '{"filename":"a.pdf","pages":["Carrier: Northstar Mutual\nCommercial General Liability: Limit $2,000,000 Deductible $2,500\nCyber Liability: Limit $1M Retention $10,000\nTotal Premium: $18,400\n"]}' | python -m json.tool
curl -s -X POST localhost:8000/api/v3/quotes $H -d '{"filename":"b.pdf","pages":["Insurer: Harbor Specialty\nCGL | Limit $1,000,000 | Deductible $5,000\nE&O - Limit $3 million\nPremium: $15,900\n"]}' | python -m json.tool
curl -s -X POST localhost:8000/api/v3/quotes/compare $H -d '{"quote_ids":[1,2]}' | python -m json.tool
```

Use the `id` values printed by the first two commands if they are not 1 and 2.

Expected in the comparison:

- Cyber flagged as not quoted by Harbor Specialty.
- Professional liability flagged as not quoted by Northstar Mutual.
- General liability flagged with a lower limit for Harbor Specialty (best is $2,000,000).
- "CGL" and "Commercial General Liability" mapped to the same row.

### Measured result

On two hand-labeled synthetic quotes (4 coverages, 2 carriers, 2 premiums, differently worded labels), the extractor output matches the labels exactly and every value passes verification. This runs as a regression test: if extraction changes, the build fails.

This fixture is synthetic and small, so it shows the pipeline works, not that it handles real carrier documents. See the limits below.

### How the pieces map to common AI-product work

| Capability | Where it lives |
|---|---|
| Structured extraction from documents | `backend/quotes/extract.py`, `llm_extract.py` |
| Source-cited, checkable output | `backend/quotes/verify.py` |
| Turning messy labels into a standard schema | `backend/quotes/coverage.py` |
| Quote comparison and gap analysis | `backend/quotes/compare.py` |
| LLM output validated before it is shown | `llm_extract.py` (claims rejected unless the source supports them) |
| Backend API, storage, tenant isolation | `router.py`, `models.py`, migration `0003` |
| Product UI | `backend/quotes/ui.py` |
| Evaluation on labeled data | `tests/test_quotes.py` |

### Limits (stated honestly)

- **Synthetic data only.** The fixtures are made-up quotes. Real carrier PDFs have tables, multiple columns and scanned pages that the rule-based extractor will not handle well. Do not upload real client documents to a demo deployment.
- **Text-based PDFs only.** Scanned PDFs return a clear 422 error. There is no OCR.
- **Rule-based extraction is a baseline.** It expects lines like `Cyber Liability: Limit $1M Retention $10,000`. The LLM path handles freer layouts but has only been tested with a fake model, not against the live Gemini API.
- **Citations are text spans, not bounding boxes.** The demo highlights the exact text in a text view, not on the rendered PDF page.
- **Coverage vocabulary is small.** Eight coverage types. Unknown labels stay `unmapped` and are listed in the comparison instead of being guessed.
- **Money only.** Limits and deductibles are dollar amounts. Percentages, per-occurrence versus aggregate terms and sub-limits are not modeled.
- **No embeddings in QuoteLens yet.** pgvector is used by Incident IQ (v2) but not for searching quote text.
- **Comparison is limited to coverages both quotes map to a standard name.**

---

## Part 2: GTM account resolution

### The problem

In many sales teams every rep runs their own setup. The same company sits in five private sheets under different names ("Acme GmbH", "ACME", "acme.de"), two reps call the same account in the same week, and nobody can say which account to call today.

This service fixes that one thing:

- **One account per real company.** Records from any source are normalized and merged.
- **Lineage.** Every raw record is kept with its source and how it was matched.
- **"Call today, and why."** Accounts are ranked by an explainable score; every point has a sentence attached.
- **No double outreach.** If two or more reps touched an account, it is flagged `coordinate` instead of `call_today`.

### What it does

| Capability | How |
|---|---|
| Normalize messy input | URLs and emails reduce to a registrable domain; legal suffixes and accents are stripped; free-mail and social profile domains are never used as keys |
| Resolve to one account | Same domain merges first; otherwise fuzzy name match inside the same country with no conflicting domain |
| Precision first | Short names (Stripe vs Stripes) and near-misses are not merged; they go to a review queue |
| Idempotent ingest | A record is identified by `(tenant, source, source_record_id)`, so a failed batch can be re-sent safely |
| Dead letters | Rows that cannot be loaded are saved with the reason |
| Explainable scoring | Signals, market, size and recency each add or subtract a stated number of points |

### Endpoints

All requests need `X-Tenant-Id` and `X-Api-Key`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v3/gtm/ingest` | POST | Load a batch (up to 500 records) from one source |
| `/api/v3/gtm/call-list` | GET | Ranked accounts with reasons: `?recommendation=call_today` (default), `coordinate`, `wait` or `nurture`, plus `?limit=` |
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
| 20 to 500 employees | +15 |
| Never contacted | +5 |
| No contact for 30+ days | +5 |
| Touched in the last 7 days | -25 |

Recommendation: `coordinate` if two or more reps touched the account, `wait` if touched in the last 7 days, `call_today` if the score is 50 or more, otherwise `nurture`. The weights are my assumptions, not data from any real company.

### Measured result

Duplicate detection was checked against a hand-labeled fixture of 21 records covering 9 true company pairs.

| Metric | Result |
|---|---|
| Precision | **1.00** (no wrong merges) |
| Recall | **0.89** (8 of 9 true pairs found) |

The one miss, "International Business Machines" vs "IBM Corp", is left in on purpose: no name-based method can know it. Run it with `python -m pytest tests/test_gtm_resolver.py -s`.

### Limits

- Each batch loads a tenant's accounts into memory; beyond thousands of accounts, add a `pg_trgm` index.
- Two existing accounts that later turn out to be the same company are not auto-merged.
- Re-ingesting can add or update signals but not remove them.
- Signals arrive with the records; there is no external data pulling yet.
- Scoring is recomputed on every read, which is simple but linear in account count.

---

## Part 3: Incident IQ (original project)

**Live demo:** https://incident-iq-drab.vercel.app/dashboard

A small multi-tenant API and dashboard that takes raw error logs and returns a likely root cause, a confidence score and remediation steps.

### How it works

It is a **rule-based pattern-matching engine**, not a hosted ML model. It began as an NVIDIA Nemotron hackathon submission with a LoRA fine-tuning script (`train_lora.py`), but the deployed API does not call that model. It matches log content against known incident patterns (database exhaustion, OOM, CPU spikes, gateway failures, disk and network issues). The `reasoning_trace` field in every response shows which logic fired, so the reasoning is inspectable.

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
| `/api/tenant/incidents` | GET | Incident history for a tenant |

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

### Demo credentials

Public demo keys for the dashboard only. Never reuse them for real data.

| Tenant | API Key |
|---|---|
| `demo_corp` | `demo-key-123` |
| `test_inc` | `test-key-456` |

Each tenant has isolated data. A request with `test_inc`'s tenant ID and `demo_corp`'s key is rejected. Use your own `TENANT_KEYS` in any real deployment.

---

## Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy, Alembic, pdfplumber
- **Data:** PostgreSQL (pgvector for v2 similarity search), Redis (optional cache)
- **AI:** Gemini (embeddings in v2; optional extraction in QuoteLens) with outputs validated before display
- **Logging and quality:** structlog JSON logs, pytest, GitHub Actions CI
- **Deployment:** Vercel (serverless via Mangum), Docker, Kubernetes manifests in `k8s/`
- **Frontend:** vanilla HTML/CSS/JS, no framework

## Tests

```bash
python -m pytest -q
```

`tests/test_quotes.py` (11 tests) and the GTM tests (15) run without a database. `tests/test_v2.py` needs `DATABASE_URL` pointing at Postgres, which CI provides.

## Project structure

```
incident-iq/
├── api/app.py                  # FastAPI app, v1 routes, dashboard and reasoning engine
├── backend/
│   ├── core.py                 # settings, DB, cache, logging shared by v2 and v3
│   ├── router.py               # /api/v2 incident routes
│   ├── gtm/                    # /api/v3/gtm: normalize, resolver, scoring, service, router, models
│   └── quotes/                 # /api/v3/quotes
│       ├── money.py            #   parse "$1M", "$3 million", "$5,000"
│       ├── coverage.py         #   map carrier wording to one standard coverage name
│       ├── extract.py          #   rule-based extraction with citations
│       ├── llm_extract.py      #   optional Gemini extraction; unsupported claims rejected
│       ├── verify.py           #   citation checker
│       ├── compare.py          #   side-by-side diff and gap flags
│       ├── service.py          #   PDF text reading and the analyze pipeline
│       ├── router.py           #   FastAPI routes and tenant auth
│       ├── models.py           #   quote_documents table
│       └── ui.py               #   demo page
├── migrations/versions/        # 0001 incidents, 0002 GTM, 0003 quotes
├── tests/                      # test_v2.py, test_gtm_*.py, test_quotes.py
├── eval/ and scripts/          # labeled incident set and benchmark script
├── k8s/ and docs/              # Kubernetes manifests, ARCHITECTURE.md
├── requirements.txt            # Vercel / app dependencies
├── requirements-backend.txt    # Postgres, pgvector, pdfplumber, pytest
└── README.md
```

## Deployment

Auto-deploys to Vercel on every push to `main`. The v2 and v3 routes need Postgres: set `DATABASE_URL` and `TENANT_KEYS`, then run `PYTHONPATH=. python -m alembic upgrade head` once. PDF upload needs `pdfplumber` in the deployed environment; without it that route returns 501 and the page-text API still works.

## License

MIT, free to use, modify, and build on.

---

Built by [k-kj0](https://github.com/k-kj0).
