#!/usr/bin/env python3
"""
benchmark.py — Gravitino IRC Benchmark Suite

Tier 1: Catalog API latency — direct REST calls to the IRC endpoint.
        Measures the IRC protocol operations that RBC's comparison table used.
        Each operation is called N times; reports median and P95.

Tier 2: Query latency — Trino queries against the Iceberg table via IRC.
        Covers metadata-only, aggregation, and predicate pushdown patterns.
        Each query is run N times; reports median and P95.

Output: Console table + benchmark_results.json

Usage (via Makefile):
  make benchmark

Or directly:
  docker compose exec python python /scripts/benchmark.py
"""

import os
import sys
import json
import time
import statistics
import requests
import trino
from datetime import datetime
from tabulate import tabulate

# ── Config ────────────────────────────────────────────────────────────────────
IRC_URI     = os.environ["IRC_URI"]           # http://gravitino-irc:9001/iceberg
TRINO_HOST  = os.environ.get("TRINO_HOST", "trino")
TRINO_PORT  = int(os.environ.get("TRINO_PORT", "8080"))
NAMESPACE   = "nyc_taxi"
TABLE_NAME  = "yellow_trips"

CATALOG_API_RUNS = 10   # Tier 1: repeat each REST call this many times
QUERY_RUNS       = 5    # Tier 2: repeat each Trino query this many times


# ── Timing helpers ────────────────────────────────────────────────────────────

def timed_rest(method: str, url: str, **kwargs) -> tuple[int, float]:
    """Make a single REST call and return (status_code, elapsed_ms)."""
    t0 = time.perf_counter()
    resp = requests.request(method, url, timeout=30, **kwargs)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return resp.status_code, elapsed_ms


def run_rest_n(label: str, method: str, url: str, n: int, **kwargs) -> dict:
    """Run a REST call n times, return stats dict."""
    timings = []
    for i in range(n):
        status, ms = timed_rest(method, url, **kwargs)
        if status not in (200, 204):
            print(f"  WARNING: {label} returned HTTP {status} on run {i+1}")
        timings.append(ms)
    return {
        "label":   label,
        "runs":    n,
        "min_ms":  round(min(timings), 2),
        "median_ms": round(statistics.median(timings), 2),
        "p95_ms":  round(sorted(timings)[int(n * 0.95)], 2),
        "max_ms":  round(max(timings), 2),
    }


def timed_trino(cursor, sql: str) -> float:
    """Execute a Trino query and return elapsed wall-clock ms."""
    t0 = time.perf_counter()
    cursor.execute(sql)
    rows = cursor.fetchall()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return elapsed_ms, rows


def run_trino_n(label: str, cursor, sql: str, n: int) -> dict:
    """Run a Trino query n times, return stats dict."""
    timings = []
    for i in range(n):
        ms, rows = timed_trino(cursor, sql)
        timings.append(ms)
        if i == 0:
            print(f"    Run 1 result: {rows[:2]}{'...' if len(rows) > 2 else ''}")
    return {
        "label":     label,
        "runs":      n,
        "min_ms":    round(min(timings), 2),
        "median_ms": round(statistics.median(timings), 2),
        "p95_ms":    round(sorted(timings)[int(n * 0.95)], 2),
        "max_ms":    round(max(timings), 2),
        "sql":       sql.strip(),
    }


# ── Tier 1: Catalog API latency ───────────────────────────────────────────────

def run_tier1() -> list[dict]:
    print(f"\n{'='*60}")
    print(f"  TIER 1 — Catalog API Latency  ({CATALOG_API_RUNS} runs each)")
    print(f"  IRC endpoint: {IRC_URI}")
    print(f"{'='*60}")

    base = IRC_URI
    results = []

    # 1. Config fetch — /v1/config
    print(f"\n[1] GET /v1/config ...")
    r = run_rest_n("GET /v1/config", "GET", f"{base}/v1/config", CATALOG_API_RUNS)
    results.append(r); print(f"    median: {r['median_ms']}ms  p95: {r['p95_ms']}ms")

    # 2. List namespaces — /v1/namespaces
    print(f"\n[2] GET /v1/namespaces ...")
    r = run_rest_n("GET /v1/namespaces", "GET", f"{base}/v1/namespaces", CATALOG_API_RUNS)
    results.append(r); print(f"    median: {r['median_ms']}ms  p95: {r['p95_ms']}ms")

    # 3. Get namespace — /v1/namespaces/{ns}
    print(f"\n[3] GET /v1/namespaces/{NAMESPACE} ...")
    r = run_rest_n(f"GET /v1/namespaces/{NAMESPACE}", "GET",
                   f"{base}/v1/namespaces/{NAMESPACE}", CATALOG_API_RUNS)
    results.append(r); print(f"    median: {r['median_ms']}ms  p95: {r['p95_ms']}ms")

    # 4. List tables — /v1/namespaces/{ns}/tables
    print(f"\n[4] GET /v1/namespaces/{NAMESPACE}/tables ...")
    r = run_rest_n(f"GET /v1/namespaces/{NAMESPACE}/tables", "GET",
                   f"{base}/v1/namespaces/{NAMESPACE}/tables", CATALOG_API_RUNS)
    results.append(r); print(f"    median: {r['median_ms']}ms  p95: {r['p95_ms']}ms")

    # 5. Load table — /v1/namespaces/{ns}/tables/{table}  ← THE key IRC operation
    print(f"\n[5] GET /v1/namespaces/{NAMESPACE}/tables/{TABLE_NAME}  (loadTable) ...")
    r = run_rest_n(f"loadTable ({TABLE_NAME})", "GET",
                   f"{base}/v1/namespaces/{NAMESPACE}/tables/{TABLE_NAME}",
                   CATALOG_API_RUNS)
    results.append(r); print(f"    median: {r['median_ms']}ms  p95: {r['p95_ms']}ms")

    # 6. Load table warm path — same call 10 more times back-to-back
    print(f"\n[6] loadTable warm path (10 consecutive calls) ...")
    r = run_rest_n(f"loadTable warm path", "GET",
                   f"{base}/v1/namespaces/{NAMESPACE}/tables/{TABLE_NAME}", 10)
    results.append(r); print(f"    median: {r['median_ms']}ms  p95: {r['p95_ms']}ms")

    return results


# ── Tier 2: Trino query latency ───────────────────────────────────────────────

def run_tier2() -> list[dict]:
    print(f"\n{'='*60}")
    print(f"  TIER 2 — Trino Query Latency  ({QUERY_RUNS} runs each)")
    print(f"  Trino: {TRINO_HOST}:{TRINO_PORT}")
    print(f"{'='*60}")

    conn = trino.dbapi.connect(
        host=TRINO_HOST,
        port=TRINO_PORT,
        user="benchmark",
        catalog="gravitino_irc",
        schema=NAMESPACE,
    )
    cur = conn.cursor()
    results = []

    queries = [
        (
            "SHOW SCHEMAS",
            "SHOW SCHEMAS IN gravitino_irc",
        ),
        (
            "SHOW TABLES",
            f"SHOW TABLES IN gravitino_irc.{NAMESPACE}",
        ),
        (
            "DESCRIBE table",
            f"DESCRIBE gravitino_irc.{NAMESPACE}.{TABLE_NAME}",
        ),
        (
            "COUNT(*)",
            f"SELECT COUNT(*) FROM gravitino_irc.{NAMESPACE}.{TABLE_NAME}",
        ),
        (
            "payment_type aggregation",
            f"""
            SELECT payment_type, COUNT(*), ROUND(AVG(total_amount), 2)
            FROM gravitino_irc.{NAMESPACE}.{TABLE_NAME}
            GROUP BY payment_type
            ORDER BY 2 DESC
            """,
        ),
        (
            "avg fare by month",
            f"""
            SELECT
                MONTH(tpep_pickup_datetime) AS month,
                COUNT(*) AS trips,
                ROUND(AVG(fare_amount), 2) AS avg_fare,
                ROUND(AVG(trip_distance), 2) AS avg_distance
            FROM gravitino_irc.{NAMESPACE}.{TABLE_NAME}
            WHERE YEAR(tpep_pickup_datetime) = 2024
            GROUP BY MONTH(tpep_pickup_datetime)
            ORDER BY 1
            """,
        ),
        (
            "top pickup locations",
            f"""
            SELECT PULocationID, COUNT(*) AS trips
            FROM gravitino_irc.{NAMESPACE}.{TABLE_NAME}
            GROUP BY PULocationID
            ORDER BY 2 DESC
            LIMIT 10
            """,
        ),
    ]

    for label, sql in queries:
        print(f"\n[Q] {label} ...")
        r = run_trino_n(label, cur, sql, QUERY_RUNS)
        results.append(r)
        print(f"    median: {r['median_ms']}ms  p95: {r['p95_ms']}ms")

    conn.close()
    return results


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(tier1: list[dict], tier2: list[dict]):
    print(f"\n{'='*60}")
    print(f"  BENCHMARK RESULTS — Gravitino IRC 1.2.0")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*60}")

    headers = ["Operation", "Runs", "Min (ms)", "Median (ms)", "P95 (ms)", "Max (ms)"]

    print(f"\n--- Tier 1: Catalog API Latency (direct REST) ---")
    t1_rows = [[r["label"], r["runs"], r["min_ms"], r["median_ms"],
                r["p95_ms"], r["max_ms"]] for r in tier1]
    print(tabulate(t1_rows, headers=headers, tablefmt="github"))

    print(f"\n--- Tier 2: Trino Query Latency ---")
    t2_rows = [[r["label"], r["runs"], r["min_ms"], r["median_ms"],
                r["p95_ms"], r["max_ms"]] for r in tier2]
    print(tabulate(t2_rows, headers=headers, tablefmt="github"))

    # Save JSON
    output = {
        "gravitino_version": "1.2.0",
        "timestamp_utc": datetime.utcnow().isoformat(),
        "catalog_api_runs_per_operation": CATALOG_API_RUNS,
        "query_runs_per_operation": QUERY_RUNS,
        "tier1_catalog_api": tier1,
        "tier2_trino_queries": tier2,
    }
    with open("/tmp/benchmark_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n  Results saved to benchmark_results.json")
    print(f"{'='*60}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\nGravitino IRC Benchmark — starting")
    print(f"IRC:   {IRC_URI}")
    print(f"Trino: {TRINO_HOST}:{TRINO_PORT}")

    # Quick connectivity check
    try:
        resp = requests.get(f"{IRC_URI}/v1/config", timeout=10)
        resp.raise_for_status()
        print(f"✓ IRC reachable")
    except Exception as e:
        print(f"✗ Cannot reach IRC at {IRC_URI}: {e}")
        sys.exit(1)

    tier1 = run_tier1()
    tier2 = run_tier2()
    print_report(tier1, tier2)


if __name__ == "__main__":
    main()
