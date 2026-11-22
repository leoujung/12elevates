#!/usr/bin/env bash
# Resets an EXISTING member's password. Runs inside the API container.
# - Password generated inside the container, written to a 600-mode file on the host. Never printed.
# - Refuses if the email does not exist.
set -euo pipefail

EMAIL="$1"
OUT="$HOME/reset_password_$(echo -n "$EMAIL" | md5sum | cut -d' ' -f1).txt"

if [ -e "$OUT" ]; then
  echo "refusing: $OUT already exists (read and delete it first)" >&2
  exit 1
fi

umask 077
PASS="$(sudo -n docker exec -e APP_EMAIL="$EMAIL" infra-elevate-api-1 python -c '
import os, secrets, sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.core import Member
from app.core.security import hash_password

pw = secrets.token_urlsafe(18)
eng = create_engine(os.environ["APP_DATABASE_URL"])
with Session(eng) as db:
    m = db.scalar(select(Member).where(Member.email == os.environ["APP_EMAIL"]))
    if not m:
        print("NOT FOUND", file=sys.stderr); sys.exit(3)
    m.password_hash = hash_password(pw)
    db.commit()
print(pw)
')"

printf '%s\n' "$PASS" > "$OUT"
chmod 600 "$OUT"
echo "password reset for $EMAIL. new password written to $OUT (mode 600). Read it, then delete it."
