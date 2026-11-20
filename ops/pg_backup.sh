#!/usr/bin/env bash
# Daily logical backup of elevate_platform with 7-day local retention.
# Runs as user hermes. Uses sudo -n -u postgres (peer auth), so no password is read here.
# Output: ~/backups/pg/elevate_platform_<UTC timestamp>.dump (mode 600, dir mode 700).
set -euo pipefail

DB="elevate_platform"
DIR="$HOME/backups/pg"
KEEP_DAYS=7
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DIR/${DB}_${TS}.dump"

umask 077
mkdir -p "$DIR"
chmod 700 "$DIR"

# custom format (-Fc) supports selective and parallel restore
sudo -n -u postgres pg_dump -Fc "$DB" > "$OUT.tmp"

# refuse to keep an empty or truncated dump
if [ ! -s "$OUT.tmp" ]; then
  rm -f "$OUT.tmp"
  echo "backup FAILED: empty dump" >&2
  exit 1
fi

mv "$OUT.tmp" "$OUT"
sha256sum "$OUT" > "$OUT.sha256"

# copy off-server to Google Drive; a failed upload fails the whole job
REMOTE="gdrive-elevate:elevate-backups"
rclone copy "$OUT" "$REMOTE/" --checksum
rclone copy "$OUT.sha256" "$REMOTE/" --checksum
if ! rclone check "$OUT" "$REMOTE/" --one-way --checksum >/dev/null 2>&1; then
  echo "backup FAILED: remote copy does not match local dump" >&2
  exit 1
fi

# retention: delete local dumps older than KEEP_DAYS (remote copies are kept separately)
find "$DIR" -maxdepth 1 -name "${DB}_*.dump" -mtime +"$KEEP_DAYS" -print -delete
find "$DIR" -maxdepth 1 -name "${DB}_*.sha256" -mtime +"$KEEP_DAYS" -delete

echo "backup OK: $OUT ($(stat -c %s "$OUT") bytes) + uploaded to $REMOTE"
