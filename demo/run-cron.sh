#!/usr/bin/env bash
# Never wait on the terminal: some hermes commands ask a question when they see one.
exec < /dev/null
# Run the demo cron job once, right now, and show what it answered.
# Press it repeatedly: once the cron share of the budget is used up, the job is held.
# Usage: demo/run-cron.sh
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN="$DEMO_DIR/.run"
[ -f "$RUN/job_id" ] || { echo "先に demo/start.sh を実行してください"; exit 1; }
# shellcheck source=/dev/null
source "$DEMO_DIR/env.sh"
job="$(cat "$RUN/job_id")"
outdir="$HERMES_HOME/cron/output/$job"

count() { { find "$outdir" -name '*.md' 2>/dev/null || true; } | wc -l | tr -d ' '; }
before="$(count)"
# Do not restart the gateway here: Hermes backs off after several quick restarts (10s, 20s, 40s...).
# The job stays paused between presses so nothing fires it on its own; resume it just for this run.
hermes cron resume "$job" > /dev/null 2>&1
trap 'hermes cron pause "$job" > /dev/null 2>&1 || true' EXIT
hermes cron run "$job" > "$RUN/last_run.log" 2>&1 || { cat "$RUN/last_run.log"; exit 1; }
latest="$(ls -t "$outdir"/*.md 2>/dev/null | head -1 || true)"
after="$(count)"

echo "⏰ cron \"$(cat "$RUN/job_name")\" run #$after"
if [ -z "$latest" ] || [ "$after" = "$before" ]; then
  echo "   （出力が見つかりませんでした）"; cat "$RUN/last_run.log"; exit 1
fi
answer="$(awk 'f{print} /^## Response/{f=1}' "$latest" | sed '/^[[:space:]]*$/d')"
echo "   → $answer"
