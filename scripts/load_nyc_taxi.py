#!/usr/bin/env python3
"""
load_nyc_taxi.py — Register NYC Taxi Parquet files as an Iceberg table via Gravitino IRC.

Assumes the Parquet files have already been uploaded to S3:
  s3://${S3_BUCKET}/${S3_PREFIX}/raw/nyc_taxi/

Uses PyIceberg add_files() to register existing Parquet files without rewriting them.
This is the fastest load path and keeps the data files in their original form.

Usage (via Makefile):
  make load-data

Or directly:
  docker compose exec python python /scripts/load_nyc_taxi.py
"""

import os
import sys
import time
import boto3
import pyarrow.parquet as pq
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import (
    NestedField, LongType, DoubleType, StringType,
    TimestampType, IntegerType, FloatType
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.transforms import MonthTransform

# ── Config from environment ───────────────────────────────────────────────────
IRC_URI    = os.environ["IRC_URI"]
S3_BUCKET  = os.environ["S3_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "us-east-2")

NAMESPACE  = "nyc_taxi"
TABLE_NAME = "yellow_trips"
RAW_PREFIX = "raw/nyc_taxi/"

# ── Iceberg schema matching NYC TLC 2024 Parquet schema ──────────────────────
SCHEMA = Schema(
    NestedField(1,  "VendorID",                 LongType(),      required=False),
    NestedField(2,  "tpep_pickup_datetime",      TimestampType(), required=False),
    NestedField(3,  "tpep_dropoff_datetime",     TimestampType(), required=False),
    NestedField(4,  "passenger_count",           DoubleType(),    required=False),
    NestedField(5,  "trip_distance",             DoubleType(),    required=False),
    NestedField(6,  "RatecodeID",                DoubleType(),    required=False),
    NestedField(7,  "store_and_fwd_flag",        StringType(),    required=False),
    NestedField(8,  "PULocationID",              LongType(),      required=False),
    NestedField(9,  "DOLocationID",              LongType(),      required=False),
    NestedField(10, "payment_type",              LongType(),      required=False),
    NestedField(11, "fare_amount",               DoubleType(),    required=False),
    NestedField(12, "extra",                     DoubleType(),    required=False),
    NestedField(13, "mta_tax",                   DoubleType(),    required=False),
    NestedField(14, "tip_amount",                DoubleType(),    required=False),
    NestedField(15, "tolls_amount",              DoubleType(),    required=False),
    NestedField(16, "improvement_surcharge",     DoubleType(),    required=False),
    NestedField(17, "total_amount",              DoubleType(),    required=False),
    NestedField(18, "congestion_surcharge",      DoubleType(),    required=False),
    NestedField(19, "Airport_fee",               DoubleType(),    required=False),
)


def list_parquet_files(bucket: str, prefix: str) -> list[str]:
    """Return s3://bucket/key paths for all Parquet files under prefix."""
    s3 = boto3.client("s3", region_name=AWS_REGION)
    paginator = s3.get_paginator("list_objects_v2")
    files = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                files.append(f"s3://{bucket}/{obj['Key']}")
    return sorted(files)


def main():
    print(f"\n{'='*60}")
    print(f"  Gravitino IRC — NYC Taxi Data Loader")
    print(f"{'='*60}")
    print(f"  IRC:       {IRC_URI}")
    print(f"  S3 bucket: s3://{S3_BUCKET}/{RAW_PREFIX}")
    print(f"  Table:     {NAMESPACE}.{TABLE_NAME}")
    print()

    # ── Connect to Gravitino IRC ──────────────────────────────────────────────
    print("Connecting to Gravitino IRC...")
    catalog = load_catalog(
        "gravitino_irc",
        **{
            "type": "rest",
            "uri": IRC_URI,
            "s3.region": AWS_REGION,
        }
    )
    print("  ✓ Connected")

    # ── Create namespace ──────────────────────────────────────────────────────
    print(f"\nCreating namespace '{NAMESPACE}'...")
    try:
        catalog.create_namespace(NAMESPACE)
        print(f"  ✓ Namespace '{NAMESPACE}' created")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"  ✓ Namespace '{NAMESPACE}' already exists")
        else:
            raise

    # ── Create table (unpartitioned for simplicity) ───────────────────────────
    full_name = f"{NAMESPACE}.{TABLE_NAME}"
    print(f"\nCreating table '{full_name}'...")
    try:
        table = catalog.create_table(
            identifier=full_name,
            schema=SCHEMA,
        )
        print(f"  ✓ Table created")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"  ✓ Table already exists, loading it")
            table = catalog.load_table(full_name)
        else:
            raise

    # ── List Parquet files on S3 ──────────────────────────────────────────────
    print(f"\nListing Parquet files at s3://{S3_BUCKET}/{RAW_PREFIX} ...")
    files = list_parquet_files(S3_BUCKET, RAW_PREFIX)
    if not files:
        print(f"\n  ERROR: No Parquet files found at s3://{S3_BUCKET}/{RAW_PREFIX}")
        print(f"  Upload files first: aws s3 sync ~/data/nyc_taxi_2024/ s3://{S3_BUCKET}/{RAW_PREFIX}")
        sys.exit(1)

    print(f"  ✓ Found {len(files)} Parquet files:")
    for f in files:
        print(f"      {f}")

    # ── Register files via add_files() ───────────────────────────────────────
    print(f"\nRegistering files as Iceberg table (no data rewrite)...")
    t0 = time.time()
    table.add_files(file_paths=files)
    elapsed = time.time() - t0
    print(f"  ✓ {len(files)} files registered in {elapsed:.1f}s")

    # ── Quick validation ──────────────────────────────────────────────────────
    print(f"\nValidating table...")
    scan = table.scan()
    count = len(list(scan.to_arrow().to_pydict()["VendorID"]))
    print(f"  ✓ Row count via PyIceberg scan: {count:,}")

    print(f"\n{'='*60}")
    print(f"  Load complete. Ready to benchmark.")
    print(f"  Run: make benchmark")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
