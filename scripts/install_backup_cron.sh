#!/bin/sh
# Run only on the long-lived host that owns the Compose installation.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
case "$PROJECT_DIR" in *'%'*|*'"'*|*'`'*|*'$'*|*'\'*) printf '%s\n' 'Move deployment to a path without shell metacharacters before installing cron.' >&2; exit 2;; esac
TEMP_FILE=$(mktemp)
trap 'rm -f "$TEMP_FILE"' EXIT HUP INT TERM
mkdir -p "$PROJECT_DIR/backups"
(crontab -l 2>/dev/null || true) | sed '/# BEGIN GATHER BACKUP/,/# END GATHER BACKUP/d' > "$TEMP_FILE"
{
    printf '%s\n' '# BEGIN GATHER BACKUP'
    printf '%s\n' 'PATH=/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin'
    printf '0 2 * * * cd "%s" && /bin/sh scripts/backup.sh >> "%s/backups/backup.log" 2>&1\n' "$PROJECT_DIR" "$PROJECT_DIR"
    printf '%s\n' '# END GATHER BACKUP'
} >> "$TEMP_FILE"
crontab "$TEMP_FILE"
printf '%s\n' 'Installed daily 02:00 backup in the host timezone. Monitor backups/backup.log.'
