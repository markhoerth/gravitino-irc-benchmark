.PHONY: up down down-clean build load-data benchmark smoke-test trino-shell logs status

# ── Environment ───────────────────────────────────────────────────────────────
# Copy .env.example to .env and fill in S3_BUCKET and AWS credentials.
# On EC2 with an IAM instance role, leave AWS_ACCESS_KEY_ID and
# AWS_SECRET_ACCESS_KEY blank — the instance role provides credentials.

up:
	@echo "Starting Gravitino IRC benchmark environment (full server)..."
	docker compose up -d --build
	@echo ""
	@echo "Services:"
	@echo "  Gravitino API: http://localhost:$$(grep GRAVITINO_API_PORT .env 2>/dev/null | cut -d= -f2 || echo 8090)"
	@echo "  IRC:           http://localhost:$$(grep IRC_PORT .env | cut -d= -f2)/iceberg"
	@echo "  Trino:         http://localhost:$$(grep TRINO_PORT .env | cut -d= -f2)"
	@echo ""
	@echo "Next steps:"
	@echo "  make trino-shell  — connect to Trino CLI"
	@echo "  make load-data    — upload data to S3 and register as Iceberg table"
	@echo "  make benchmark    — run benchmark suite"

down:
	docker compose down

down-clean:
	docker compose down -v --remove-orphans
	docker image rm -f gravitino-irc-benchmark:1.2.0 2>/dev/null || true

build:
	docker compose build

# ── Data Loading ──────────────────────────────────────────────────────────────
load-data:
	docker compose exec python python /scripts/load_nyc_taxi.py

# ── Benchmark ─────────────────────────────────────────────────────────────────
benchmark:
	docker compose exec python python /scripts/benchmark.py

# ── Smoke test ────────────────────────────────────────────────────────────────
# Exercises the Trino → IRC path end-to-end (CREATE SCHEMA / CREATE TABLE /
# INSERT / SELECT / UPDATE / DELETE / ALTER TABLE / CTAS / DROP). Verifies
# the bundled hotfix JAR is in effect — on stock 1.2.0 with authorization
# enabled, CREATE TABLE would fail with NoSuchTableException.
smoke-test:
	docker compose exec -T trino trino \
		--server http://localhost:8080 \
		--catalog irc_catalog < scripts/smoke_test.sql

# ── Trino shell ───────────────────────────────────────────────────────────────
trino-shell:
	docker compose exec trino trino \
		--server http://localhost:8080 \
		--catalog irc_catalog

# ── Logs ──────────────────────────────────────────────────────────────────────
logs:
	docker compose logs -f

logs-gravitino:
	docker compose logs -f gravitino

logs-trino:
	docker compose logs -f trino

# ── Status ────────────────────────────────────────────────────────────────────
status:
	docker compose ps
