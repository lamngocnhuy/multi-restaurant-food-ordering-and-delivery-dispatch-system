#!/bin/sh
# Daily PostgreSQL logical backup for the Docker Compose installation.
set -eu
umask 077
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BACKUP_DIR=${BACKUP_DIR:-"$PROJECT_DIR/backups"}
KEEP_DAYS=${KEEP_DAYS:-30}
case "$KEEP_DAYS" in *[!0-9]*|'') printf '%s\n' 'KEEP_DAYS must be an integer.' >&2; exit 2;; esac
mkdir -p "$BACKUP_DIR"
LOCK_DIR="$BACKUP_DIR/.backup.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' 'A backup is already running; inspect backups/.backup.lock if a prior job crashed.' >&2
    exit 1
fi
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TEMP_FILE="$BACKUP_DIR/gather-$STAMP.dump.partial"
FINAL_FILE="$BACKUP_DIR/gather-$STAMP.dump"
cleanup() { rm -f "$TEMP_FILE"; rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup EXIT HUP INT TERM
cd "$PROJECT_DIR"
docker compose exec -T db sh -c 'exec pg_dump --format=custom --no-owner --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' > "$TEMP_FILE"
test -s "$TEMP_FILE"
docker compose exec -T db pg_restore --list < "$TEMP_FILE" > /dev/null
mv "$TEMP_FILE" "$FINAL_FILE"
find "$BACKUP_DIR" -type f -name 'gather-*.dump' -mtime "+$KEEP_DAYS" -exec rm -f {} \;
printf 'Backup verified: %s\n' "$FINAL_FILE"
