#!/usr/bin/env bash
# Never wait on the terminal: some hermes commands ask a question when they see one.
exec < /dev/null
# Stop the fake model server and delete the practice environment.
DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN="$DEMO_DIR/.run"
if [ -d "$RUN/home" ]; then
  (source "$DEMO_DIR/env.sh" && hermes gateway stop < /dev/null > /dev/null 2>&1) || true
fi
[ -f "$RUN/fake_model.pid" ] && kill "$(cat "$RUN/fake_model.pid")" 2>/dev/null
rm -rf "$RUN"
echo "練習用の環境を片付けました"
