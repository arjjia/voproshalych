#!/bin/bash
# Cleanup script to remove demo data from postgres-batteries-inc image
# This runs during database initialization (initdb)

set -e

DB_NAME="$POSTGRES_DB"
DB_USER="$POSTGRES_USER"

echo "Cleaning up demo schemas and tables..."

# Step 1: Create schema and enable basic extensions in postgres db
psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d postgres <<-EOSQL
    CREATE SCHEMA IF NOT EXISTS public;
EOSQL

# Step 2: Drop demo schemas (tiger, topology, etc.)
psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d postgres <<-EOSQL
    DROP SCHEMA IF EXISTS tiger CASCADE;
    DROP SCHEMA IF EXISTS tiger_data CASCADE;
    DROP SCHEMA IF EXISTS topology CASCADE;
EOSQL

# Step 3: Drop demo tables in public
psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d postgres <<-EOSQL
    DROP TABLE IF EXISTS sample_documents CASCADE;
    DROP TABLE IF EXISTS sample_locations CASCADE;
    DROP TABLE IF EXISTS sample_roads CASCADE;
    DROP TABLE IF EXISTS sample_vectors CASCADE;
EOSQL

# Step 4: Create database if different from postgres (ignore if exists)
if [ "$DB_NAME" != "postgres" ]; then
    psql -v ON_ERROR_STOP=0 -U "$DB_USER" -d postgres <<-EOSQL
        CREATE DATABASE ${DB_NAME};
EOSQL
fi

# Step 5: Enable extensions in the target database
psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<-EOSQL
    CREATE SCHEMA IF NOT EXISTS public;
    CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA public;
EOSQL

# Step 6: Update search_path (use single quotes to preserve $user)
psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" -c "ALTER DATABASE ${DB_NAME} SET search_path = ag_catalog, public, '\$user';"

echo "Cleanup completed successfully!"