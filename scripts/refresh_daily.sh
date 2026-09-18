#!/bin/sh
# Daily refresh: pull whatever OpenAlex has published since the last run and
# rebuild the tag/publication files. Roughly 5-70 requests depending on the
# window, against a 10,000/day budget.
#
# Install (optional, macOS launchd via cron compatibility):
#   crontab -e
#   15 6 * * *  /path/to/neuro-labs-explorer/scripts/refresh_daily.sh
#
# It does NOT add new PIs or institutions: that needs the full
# collect_neuro.py rebuild plus scripts/layout.mjs.
set -eu
cd "$(dirname "$0")/.."
LOG="data/cache/refresh.log"
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  python3 pipeline/enrich_text.py refresh "$@"
} >> "$LOG" 2>&1
tail -n 20 "$LOG"
