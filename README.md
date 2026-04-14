# Gravitino IRC Benchmark

Measures Apache Gravitino 1.2.0 Iceberg REST Catalog (IRC) performance against AWS S3.

## What this measures

**Tier 1 — Catalog API latency** (direct REST calls to IRC):
- `GET /v1/config` — config fetch
- `GET /v1/namespaces` — list namespaces
- `GET /v1/namespaces/{ns}` — get namespace
- `GET /v1/namespaces/{ns}/tables` — list tables
- `GET /v1/namespaces/{ns}/tables/{table}` — loadTable (the key IRC operation)
- loadTable warm path — 10 consecutive calls

**Tier 2 — Trino query latency** (via IRC):
- SHOW SCHEMAS, SHOW TABLES, DESCRIBE (metadata operations)
- COUNT(*) full scan
- Payment type aggregation
- Average fare by month
- Top pickup locations

Each operation is run multiple times; results report min, median, P95, and max.

## Stack

| Component | Version |
|-----------|---------|
| Gravitino IRC | 1.2.0 |
| MySQL (catalog backend) | 8.0 |
| Trino | 469 |
| Object store | AWS S3 (us-east-2) |
| Dataset | NYC Taxi yellow trips 2024 (12 months, ~650MB Parquet) |

## Prerequisites

- EC2 instance in `us-east-2` (recommended: `m5.2xlarge`)
- IAM instance role with S3 read/write on your benchmark bucket
- Docker + Docker Compose installed
- AWS CLI installed (for initial data upload)

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/markhoerth/gravitino-irc-benchmark.git
cd gravitino-irc-benchmark
cp .env.example .env
# Edit .env — set S3_BUCKET and S3_PREFIX at minimum
```

### 2. Upload NYC Taxi data to S3

From your laptop (or any machine with the Parquet files):

```bash
aws s3 sync ~/data/nyc_taxi_2024/ s3://YOUR_BUCKET/YOUR_PREFIX/raw/nyc_taxi/
```

### 3. Start services

```bash
make up
```

### 4. Register data as Iceberg table

```bash
make load-data
```

This uses PyIceberg `add_files()` to register the existing Parquet files as an
Iceberg table via Gravitino IRC — no data rewrite, just metadata registration.

### 5. Run benchmark

```bash
make benchmark
```

Results are printed to console and saved to `benchmark_results.json`.

## Other commands

```bash
make trino-shell    # interactive Trino SQL shell
make logs-irc       # tail Gravitino IRC logs
make status         # show service health
make down-clean     # stop and wipe all volumes
```
