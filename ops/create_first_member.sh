#!/usr/bin/env bash
# Creates the first organization + member in elevate_platform.
# - Password is generated on the server and written to a 600-mode file. It is never printed.
# - Refuses to run if the email already exists (no overwrite).
set -euo pipefail

EMAIL="$1"
NAME="$2"
OUT="$HOME/first_member_password.txt"

if [ -e "$OUT" ]; then
  echo "refusing: $OUT already exists (read and delete it first)" >&2
  exit 1
fi

umask 077
PASS="$(sudo -n docker exec -e APP_EMAIL="$EMAIL" -e APP_NAME="$NAME" infra-elevate-api-1 python -c '
import os, secrets, sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.core import Member, Organization
from app.core.security import hash_password

pw = secrets.token_urlsafe(18)
eng = create_engine(os.environ["APP_DATABASE_URL"])
with Session(eng) as db:
    if db.scalar(select(Member).where(Member.email == os.environ["APP_EMAIL"])):
        print("EXISTS", file=sys.stderr); sys.exit(3)
    org = Organization(name="12ELEVATE Pilot")
    db.add(org); db.flush()
    db.add(Member(organization_id=org.id, email=os.environ["APP_EMAIL"],
                  display_name=os.environ["APP_NAME"], password_hash=hash_password(pw)))
    db.commit()
print(pw)
')"

printf '%s\n' "$PASS" > "$OUT"
chmod 600 "$OUT"
echo "member created. password written to $OUT (mode 600). Read it, then delete it."
