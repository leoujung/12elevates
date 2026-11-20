#!/usr/bin/env bash
# Read-only pre-check before creating the first member. Prints counts only, no row data.
set -euo pipefail
EMAIL="$1"
for t in organizations members prospects consent_records audit_logs; do
  printf '%s: ' "$t"
  sudo -n -u postgres psql -d elevate_platform -tAc "select count(*) from $t"
done
printf 'member with this email already exists: '
sudo -n -u postgres psql -d elevate_platform -tAc "select count(*) from members where email = '$EMAIL'"
