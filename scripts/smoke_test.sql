-- ─────────────────────────────────────────────────────────────────────────────
-- smoke_test.sql — end-to-end exercise of Trino → Gravitino IRC with the
-- bundled hotfix JAR applied.
--
-- Every statement below failed against stock Gravitino 1.2.0 when
-- authorization was enabled (NoSuchTableException on CREATE TABLE, which
-- blocked the rest of the flow). With the hotfix JAR the full sequence
-- completes cleanly.
--
-- Run with:   make smoke-test
--
-- Prerequisite: services are up (make up) and S3_BUCKET is configured.
-- This does NOT require the NYC Taxi dataset — it creates its own
-- disposable schema and tables, and drops everything at the end.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS irc_catalog.smoke_test;

USE irc_catalog.smoke_test;

-- CREATE TABLE — the primary bug path. Stock 1.2.0 fails here with
-- "NoSuchTableException" when authorization is enabled because
-- IcebergTableHookDispatcher.createTable() calls importTable() before
-- the staged create has committed.
CREATE TABLE IF NOT EXISTS people (
    id   BIGINT,
    name VARCHAR,
    ts   TIMESTAMP(6)
);

DESCRIBE people;

-- INSERT — writes data files + a new snapshot through the IRC.
INSERT INTO people VALUES
    (1, 'alice', CURRENT_TIMESTAMP),
    (2, 'bob',   CURRENT_TIMESTAMP);

SELECT * FROM people ORDER BY id;

-- UPDATE and DELETE — exercise the updateTable commit path, which is
-- where the hotfix now invokes importTableAndSetOwner.
UPDATE people SET name = 'alice2' WHERE id = 1;
DELETE FROM people WHERE id = 2;

SELECT * FROM people ORDER BY id;

-- ALTER TABLE — schema evolution through the IRC.
ALTER TABLE people ADD COLUMN email VARCHAR;

SELECT * FROM people ORDER BY id;

-- CTAS — another code path that goes through createTable.
CREATE TABLE people_copy AS SELECT * FROM people;

SELECT COUNT(*) AS copy_rows FROM people_copy;

-- Clean up.
DROP TABLE people_copy;
DROP TABLE people;
DROP SCHEMA irc_catalog.smoke_test;
