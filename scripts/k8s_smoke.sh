#!/usr/bin/env bash
# Smoke test against a cluster where k8s/ is applied. Used by .github/workflows/k8s.yml.
set -euo pipefail

kubectl rollout status statefulset/db --timeout=180s
kubectl rollout status deployment/redis --timeout=120s
kubectl rollout status deployment/incident-iq --timeout=240s

kubectl port-forward svc/incident-iq 8080:80 >/tmp/pf.log 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null || true' EXIT
for i in $(seq 1 20); do curl -fs localhost:8080/health >/dev/null && break || sleep 1; done

echo "== /health";  curl -fsS localhost:8080/health; echo
echo "== /api/v2/ready"; curl -fsS localhost:8080/api/v2/ready; echo
echo "== /api/v2/analyze"
curl -fsS -X POST localhost:8080/api/v2/analyze -H 'Content-Type: application/json' -d '{
  "alert": {"service": "payment-api", "error": "Connection timeout",
            "logs": "ERROR: database connection pool exhausted. Active connections: 50/50."},
  "tenant_id": "demo_corp", "api_key": "demo-key-123"}' | tee /tmp/analyze.json
echo
grep -qi "pool" /tmp/analyze.json
echo "== tenant isolation (wrong key must be 401)"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST localhost:8080/api/v2/analyze -H 'Content-Type: application/json' -d '{
  "alert": {"service": "x", "error": "x"}, "tenant_id": "test_inc", "api_key": "demo-key-123"}')
test "$code" = "401"
echo "smoke test passed"
