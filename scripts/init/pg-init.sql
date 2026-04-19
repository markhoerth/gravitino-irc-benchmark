-- ─────────────────────────────────────────────────────────────────────────────
-- pg-init.sql — runs once on fresh Postgres volume.
--
-- POSTGRES_DB (iceberg_catalog) is auto-created by the postgres image.
-- This script creates the second database for Gravitino's entity store
-- and initializes its schema. Gravitino does NOT auto-create its schema.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE DATABASE gravitino_meta;
GRANT ALL PRIVILEGES ON DATABASE gravitino_meta TO iceberg;

-- Switch to gravitino_meta and initialize the Gravitino schema
\c gravitino_meta
\i /docker-entrypoint-initdb.d/02-gravitino-schema.sql
