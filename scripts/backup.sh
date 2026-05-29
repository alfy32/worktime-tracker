#!/bin/bash
set -euo pipefail

DB="/var/lib/worktime-tracker/worktime.db"
BACKUP_DIR="/var/lib/worktime-tracker/backups"
KEEP_DAYS=30

mkdir -p "$BACKUP_DIR"
cp "$DB" "$BACKUP_DIR/worktime-$(date +%Y%m%d).db"
find "$BACKUP_DIR" -name "worktime-*.db" -mtime +"$KEEP_DAYS" -delete

echo "Backup complete: $BACKUP_DIR/worktime-$(date +%Y%m%d).db"
