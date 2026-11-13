#!/bin/bash
# Exécuté UNE seule fois, au premier démarrage du conteneur PostgreSQL (volume vide).
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE DATABASE airflow;
CREATE ROLE bi_reader LOGIN PASSWORD '${BI_READER_PASSWORD}';
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO bi_reader;
GRANT USAGE ON SCHEMA public TO bi_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public GRANT SELECT ON TABLES TO bi_reader;
EOSQL
