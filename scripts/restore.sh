#!/bin/sh
# Deliberately requires an explicit destructive-operation flag.
set -eu
if [ "$#" -ne 2 ] || [ "$2" != "--yes-erases-current-data" ]; then
    printf '%s\n' 'Usage: scripts/restore.sh /absolute/path/backup.dump --yes-erases-current-data' >&2
    exit 2
fi
BACKUP_FILE=$1
test -r "$BACKUP_FILE" || { printf '%s\n' 'Backup file is not readable.' >&2; exit 1; }
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"
docker compose exec -T db pg_restore --list < "$BACKUP_FILE" > /dev/null
printf '%s\n' 'Backup readable. Stopping the app before restoring database contents.'
docker compose stop app
if docker compose exec -T db sh -c 'exec pg_restore --clean --if-exists --single-transaction --exit-on-error --no-owner --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' < "$BACKUP_FILE"; then
    docker compose up -d app
    printf '%s\n' 'Restore completed. Check /health and an existing order before reopening traffic.'
else
    printf '%s\n' 'Restore failed and transaction rolled back. App remains stopped for inspection.' >&2
    exit 1
fi
