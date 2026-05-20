#!/bin/bash
# Automatic Apache AGE OID fix after pg_restore
#
# After restoring a PostgreSQL dump, AGE graphs may have stale OIDs
# because pg_restore assigns new OIDs to schemas while ag_graph
# still holds the old ones. This script detects and fixes mismatches
# for all AGE graphs automatically.
#
# Usage:
#   docker compose exec -T postgres bash < scripts/fix_age_oid.sh
#
# Or locally:
#   PGUSER=voproshalych PGDATABASE=voproshalych bash scripts/fix_age_oid.sh

set -euo pipefail

DB_USER="${PGUSER:-${POSTGRES_USER:-voproshalych}}"
DB_NAME="${PGDATABASE:-${POSTGRES_DB:-voproshalych}}"
DB_HOST="${PGHOST:-localhost}"
DB_PORT="${PGPORT:-5432}"

PSQL=(psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -p "$DB_PORT" -v ON_ERROR_STOP=1)

echo "=== AGE OID diagnostic ==="

"${PSQL[@]}" -c "
LOAD 'age';
SET search_path = ag_catalog, public;
SELECT g.name, g.graphid AS graph_oid, n.oid AS namespace_oid,
       CASE WHEN g.graphid = n.oid THEN 'OK' ELSE 'MISMATCH' END AS status
FROM ag_graph g
JOIN pg_catalog.pg_namespace n ON n.nspname = g.name
ORDER BY g.name;
"

echo ""
echo "=== Fixing mismatches ==="

"${PSQL[@]}" <<-'EOSQL'
    LOAD 'age';
    SET search_path = ag_catalog, public;
    DO $fix$
    DECLARE
        g record;
        new_oid oid;
        fixed int := 0;
    BEGIN
        FOR g IN SELECT name, graphid FROM ag_graph LOOP
            SELECT n.oid INTO new_oid
            FROM pg_catalog.pg_namespace n
            WHERE n.nspname = g.name;

            IF new_oid IS NULL THEN
                RAISE WARNING 'Graph "%" has no matching namespace — skipping', g.name;
            ELSIF new_oid != g.graphid THEN
                RAISE NOTICE 'Fixing graph "%": graphid % -> %', g.name, g.graphid, new_oid;
                SET session_replication_role = 'replica';
                UPDATE ag_catalog.ag_label
                SET graph = new_oid
                WHERE graph = g.graphid;
                UPDATE ag_catalog.ag_graph
                SET graphid = new_oid
                WHERE name = g.name;
                SET session_replication_role = 'origin';
                fixed := fixed + 1;
            END IF;
        END LOOP;
        RAISE NOTICE 'Fixed % AGE graph(s)', fixed;
    END;
    $fix$;
EOSQL

echo ""
echo "=== Verification ==="

"${PSQL[@]}" -c "
LOAD 'age';
SET search_path = ag_catalog, public;
SELECT g.name, g.graphid AS graph_oid, n.oid AS namespace_oid,
       CASE WHEN g.graphid = n.oid THEN 'OK' ELSE 'MISMATCH' END AS status
FROM ag_graph g
JOIN pg_catalog.pg_namespace n ON n.nspname = g.name
ORDER BY g.name;
"

echo ""
echo "=== Done ==="
