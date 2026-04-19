#!/bin/bash
###############################################################################
# Gravitino Full Server Startup
#
# 1. Generates gravitino.conf from environment variables
# 2. Launches background process to create metalake + catalog after startup
# 3. Runs the Gravitino server in foreground (required for Docker)
###############################################################################
set -e

GRAVITINO_HOME="/root/gravitino"
CONF_FILE="${GRAVITINO_HOME}/conf/gravitino.conf"

# ── Step 0: Wait for PostgreSQL to actually accept connections ───────────────
# Even though docker-compose's healthcheck says postgres is ready, there can
# be a brief window on first boot where the JDBC driver gets connection-refused.
# Guard against that with a TCP probe loop.
echo "[gravitino-start] Waiting for PostgreSQL on postgres:5432..."
PG_WAIT=0
until bash -c "</dev/tcp/postgres/5432" 2>/dev/null; do
  sleep 2
  PG_WAIT=$((PG_WAIT + 2))
  if [ ${PG_WAIT} -ge 120 ]; then
    echo "[gravitino-start] ERROR: PostgreSQL not reachable after 120s"; exit 1
  fi
done
echo "[gravitino-start] PostgreSQL reachable (waited ${PG_WAIT}s)"

# ── Step 1: Generate gravitino.conf ──────────────────────────────────────────
cat > "${CONF_FILE}" <<EOF
# ── Server ───────────────────────────────────────────────────────────────────
gravitino.server.webserver.host = 0.0.0.0
gravitino.server.webserver.httpPort = 8090

# ── Entity Store (PostgreSQL) ────────────────────────────────────────────────
gravitino.entity.store = relational
gravitino.entity.store.relational.jdbcUrl = ${GRAVITINO_ENTITY_STORE_URL}
gravitino.entity.store.relational.jdbcUser = ${GRAVITINO_ENTITY_STORE_USER}
gravitino.entity.store.relational.jdbcPassword = ${GRAVITINO_ENTITY_STORE_PASSWORD}
gravitino.entity.store.relational.jdbcDriver = org.postgresql.Driver

# ── IRC Auxiliary Service ────────────────────────────────────────────────────
gravitino.auxService.names = iceberg-rest
gravitino.iceberg-rest.classpath = iceberg-rest-server/libs, iceberg-rest-server/conf
gravitino.iceberg-rest.host = 0.0.0.0
gravitino.iceberg-rest.httpPort = 9001

# Dynamic config provider — IRC delegates to Gravitino catalog framework.
# This is what triggers the hook/dispatcher chain (IcebergTableHookDispatcher).
gravitino.iceberg-rest.catalog-config-provider = dynamic-config-provider
gravitino.iceberg-rest.gravitino-uri = http://127.0.0.1:8090
gravitino.iceberg-rest.gravitino-metalake = ${GRAVITINO_METALAKE:-benchmark}
gravitino.iceberg-rest.default-catalog-name = ${GRAVITINO_CATALOG_NAME:-irc_catalog}

# ── Auth ─────────────────────────────────────────────────────────────────────
gravitino.authenticators = simple
gravitino.authorization.enable = true
gravitino.authorization.serviceAdmins = gravitino,anonymous
EOF

echo "[gravitino-start] Config generated at ${CONF_FILE}"

# ── Step 2: Background process to create metalake + catalog after server starts
(
  METALAKE="${GRAVITINO_METALAKE:-benchmark}"
  CATALOG="${GRAVITINO_CATALOG_NAME:-irc_catalog}"
  API="http://127.0.0.1:8090/api"

  # Wait for server to be ready
  MAX_WAIT=120
  WAITED=0
  until curl -sf "${API}/version" > /dev/null 2>&1; do
    sleep 2
    WAITED=$((WAITED + 2))
    if [ ${WAITED} -ge ${MAX_WAIT} ]; then
      echo "[gravitino-setup] ERROR: Server did not start within ${MAX_WAIT}s"
      exit 1
    fi
  done
  echo "[gravitino-setup] Server is healthy (waited ${WAITED}s)"

  echo "[gravitino-setup] Creating metalake '${METALAKE}'..."
  curl -sf -X POST "${API}/metalakes" \
    -H "Content-Type: application/json" \
    -H "Gravitino-User: gravitino" \
    -d "{
      \"name\": \"${METALAKE}\",
      \"comment\": \"IRC Benchmark metalake\"
    }" > /dev/null 2>&1 || echo "[gravitino-setup] Metalake may already exist"

  echo "[gravitino-setup] Creating catalog '${CATALOG}'..."
  curl -sf -X POST "${API}/metalakes/${METALAKE}/catalogs" \
    -H "Content-Type: application/json" \
    -H "Gravitino-User: gravitino" \
    -d "{
      \"name\": \"${CATALOG}\",
      \"type\": \"RELATIONAL\",
      \"provider\": \"lakehouse-iceberg\",
      \"comment\": \"Iceberg catalog with JDBC backend\",
      \"properties\": {
        \"catalog-backend\": \"jdbc\",
        \"uri\": \"${GRAVITINO_IRC_JDBC_URL}\",
        \"jdbc-user\": \"${GRAVITINO_IRC_JDBC_USER}\",
        \"jdbc-password\": \"${GRAVITINO_IRC_JDBC_PASSWORD}\",
        \"jdbc-driver\": \"org.postgresql.Driver\",
        \"jdbc-initialize\": \"true\",
        \"warehouse\": \"${GRAVITINO_WAREHOUSE}\",
        \"io-impl\": \"org.apache.iceberg.aws.s3.S3FileIO\",
        \"credential-providers\": \"s3-secret-key\",
        \"s3-secret-key-credential-provider-type\": \"S3_SECRET_KEY\",
        \"s3-access-key-id\": \"${GRAVITINO_S3_ACCESS_KEY}\",
        \"s3-secret-access-key\": \"${GRAVITINO_S3_SECRET_KEY}\",
        \"s3-region\": \"${GRAVITINO_S3_REGION:-us-east-2}\"
      }
    }" > /dev/null 2>&1 || echo "[gravitino-setup] Catalog may already exist"

  echo "[gravitino-setup] Ready. IRC: http://localhost:9001/iceberg/ | API: http://localhost:8090/api"
) &

# ── Step 3: Start server in foreground ───────────────────────────────────────
cd "${GRAVITINO_HOME}"
export GRAVITINO_HOME
JAVA_OPTS+=" -XX:-UseContainerSupport"
export JAVA_OPTS

exec ./bin/gravitino.sh run
