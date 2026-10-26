# Incident IQ architecture

## Two runtimes, one codebase

| Runtime | Entry | Storage | Use |
|---|---|---|---|
| Vercel serverless | `api/app.py` via Mangum | in-memory per tenant, resets on cold start | public demo (`/api/analyze`) |
| Docker / Kubernetes | `uvicorn api.app:app` | Postgres 16 + pgvector, Redis | v2 API (`/api/v2/*`) |

`api/app.py` always serves the v1 routes. At import time it tries to mount the v2 router from `backend/`; if the package or a database is unavailable (Vercel) it skips quietly and v1 keeps working.

## v2 request flow (`POST /api/v2/analyze`)

1. `_auth` checks `tenant_id` + `api_key` with `hmac.compare_digest` (401 on mismatch).
2. The rule-based `IncidentReasoningEngine` produces root cause, confidence, remediation steps and a reasoning trace; latency is measured, not hard-coded.
3. `embed()` calls Gemini `gemini-embedding-001` (768 dims). With no key or on failure it returns `None` and the incident is stored without a vector.
4. The incident row is written to Postgres (`incidents`, HNSW cosine index on `embedding`).
5. `POST /api/v2/incidents/similar` embeds the query and runs a cosine-distance search scoped to the tenant, cached in Redis for 60 s.

## Failure modes and degradation

| Failure | Behaviour |
|---|---|
| No `GEMINI_API_KEY` / embedding call fails | warning logged, incident saved without vector, similarity returns `mode: unavailable` |
| Redis unavailable | cache read/write errors are logged and bypassed; request still succeeds |
| Postgres unavailable | `/api/v2/ready` fails, Kubernetes removes the pod from the Service; `/health` stays up so the pod is not restarted needlessly |
| Cross-tenant access | rejected at `_auth`; every query filters on `tenant_id` |

## Observability

`structlog` emits JSON logs. Request middleware logs `request_id` (taken from `x-request-id` or generated), method, path, status and duration in ms, and returns the id in the response header.

## Deployment (Kubernetes)

`k8s/` holds a Kustomize base: Postgres StatefulSet, Redis, and the API Deployment (2 replicas, rolling update with `maxUnavailable: 0`, an init container running `alembic upgrade head`, liveness on `/health`, readiness on `/api/v2/ready`, non-root user, dropped capabilities), plus an HPA and a PodDisruptionBudget. `.github/workflows/k8s.yml` builds the image, loads it into a `kind` cluster, applies the manifests and runs `scripts/k8s_smoke.sh`.

## Debugging runbook

```bash
kubectl get pods -o wide
kubectl logs deploy/incident-iq -c migrate          # migration problems
kubectl logs deploy/incident-iq -c api --tail=100   # JSON request logs
kubectl describe pod -l app=incident-iq             # probe failures, OOMKilled
kubectl port-forward svc/incident-iq 8080:80 && curl localhost:8080/api/v2/ready
```
