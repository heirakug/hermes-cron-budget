#!/usr/bin/env bash
# Render demo/video/cron-budget-demo.mp4 from demo.tape.
# The practice environment is built outside the recording: `hermes cron create` stalls inside VHS.
set -euo pipefail
cd "$(dirname "$0")/../.."
demo/start.sh > /dev/null
trap 'demo/stop.sh > /dev/null' EXIT
vhs demo/video/demo.tape
echo "→ demo/video/cron-budget-demo.mp4"
