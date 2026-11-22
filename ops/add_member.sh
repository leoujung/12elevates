#!/usr/bin/env bash
# Adds a member to the EXISTING pilot organization (no new org). Runs inside the API container.
# - Password generated inside the container, written to a 600-mode file on the host. Never printed.
# - Refuses if the email already exists or if the organization count is not exactly 1.
set -euo pipefail

EMAIL="$1"
NAME="$2"
OUT="$HOME/added_member_password.txt"

if [ -e "$OUT" ]; then
  echo "refusing: $OUT already exists (read and delete it first)" >&2
  exit 1
fi

umask 077
PASS="$(sudo -n docker exec -e APP_EMAIL="$EMAIL" -e APP_NAME="$NAME" infra-elevate-api-1 python -c '
import os, secrets, sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.models.core import Member, Organization
from app.core.security import hash_password

pw = secrets.token_urlsafe(18)
eng = create_engine(os.environ["APP_DATABASE_URL"])
with Session(eng) as db:
    if db.scalar(select(Member).where(Member.email == os.environ["APP_EMAIL"])):
        print("EXISTS", file=sys.stderr); sys.exit(3)
    orgs = db.scalars(select(Organization)).all()
    if len(orgs) != 1:
        print("expected exactly 1 organization, found %d" % len(orgs), file=sys.stderr); sys.exit(4)
    db.add(Member(organization_id=orgs[0].id, email=os.environ["APP_EMAIL"],
                  display_name=os.environ["APP_NAME"], password_hash=hash_password(pw)))
    db.commit()
print(pw)
')"

printf '%s\n' "$PASS" > "$OUT"
chmod 600 "$OUT"
echo "member added. password written to $OUT (mode 600). Read it, then delete it."
