"""Usage: python scripts/eval_and_bench.py http://localhost:8000 eval/labeled.json
Even-numbered rows are seeded as history, odd-numbered rows are used as queries.
Needs GEMINI_API_KEY set on the server, otherwise vector search is unavailable."""
import json
import statistics
import sys
import time

import httpx

base, path = sys.argv[1], sys.argv[2]
auth = {"tenant_id": "demo_corp", "api_key": "demo-key-123"}
data = json.load(open(path))
seed, queries = data[0::2], data[1::2]

with httpx.Client(timeout=30) as c:
    for d in seed:
        c.post(f"{base}/api/v2/analyze", json={
            "alert": {k: d[k] for k in ("service", "error", "logs")}, **auth,
        }).raise_for_status()

    hits, cold, warm, modes = 0, [], [], set()
    for q in queries:
        body = {**auth, "query": f"{q['service']}\n{q['error']}\n{q['logs']}", "k": 5}
        t = time.perf_counter()
        res = c.post(f"{base}/api/v2/incidents/similar", json=body).json()
        cold.append((time.perf_counter() - t) * 1000)
        modes.add(res["mode"])
        hits += any(i["root_cause"] == q["label"] for i in res["items"])
        t = time.perf_counter()  # same query again: served from Redis if enabled
        c.post(f"{base}/api/v2/incidents/similar", json=body)
        warm.append((time.perf_counter() - t) * 1000)


def p95(xs):
    return statistics.quantiles(xs, n=20)[18] if len(xs) >= 2 else xs[0]


print(f"seeded={len(seed)} queries={len(queries)} modes={modes}")
if modes != {"vector"}:
    print("WARNING: vector search was unavailable. Set GEMINI_API_KEY on the server.")
print(f"hit rate@5 = {hits}/{len(queries)} = {hits / len(queries):.2f}")
print(f"first call ms: p50={statistics.median(cold):.0f} p95={p95(cold):.0f}")
print(f"repeat call ms: p50={statistics.median(warm):.0f} p95={p95(warm):.0f}")
