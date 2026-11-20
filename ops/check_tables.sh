#!/usr/bin/env bash
# Read-only check: list public tables in a database on the VPS.
# Usage: check_tables.sh <database>
set -euo pipefail
DB="$1"
sudo -n -u postgres psql -d "$DB" -tAc "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1;" | paste -sd' ' -
