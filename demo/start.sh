#!/usr/bin/env bash
# Never wait on the terminal: some hermes commands ask a question when they see one.
exec < /dev/null
# Build a practice Hermes environment for the demo video:
#   - a separate HERMES_HOME under demo/.run/home (your ~/.hermes is not touched)
#   - a demo dummy model on 127.0.0.1 (no real quota is spent)
#   - the cron-budget plugin installed from this checkout
#   - a small budget in observe mode, and one "every 5 minutes" cron job
# Run again at any time to start over from a clean state.
# Usage: demo/start.sh   (override with DAILY_LIMIT=10 CHAT_RESERVE=4 PORT=18765)
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$DEMO_DIR")"
RUN="$DEMO_DIR/.run"
HOME_DIR="$RUN/home"
PORT="${PORT:-18765}"
DAILY_LIMIT="${DAILY_LIMIT:-10}"
CHAT_RESERVE="${CHAT_RESERVE:-4}"
JOB_NAME="${JOB_NAME:-morning-news}"

# shellcheck source=/dev/null
source "$DEMO_DIR/env.sh"

# Stop what a previous run left behind (gateway, fake server), then wipe the practice home.
[ -f "$HOME_DIR/gateway.pid" ] && hermes gateway stop < /dev/null > /dev/null 2>&1 || true
if [ -f "$RUN/fake_model.pid" ]; then
  kill "$(cat "$RUN/fake_model.pid")" 2>/dev/null || true
  rm -f "$RUN/fake_model.pid"
fi
rm -rf "$RUN"
mkdir -p "$HOME_DIR/plugins" "$HOME_DIR/plugin-data/cron-budget"

# 1. Demo dummy model (log: demo/.run/fake_model.log — `tail -f` it in a side pane).
python3 "$DEMO_DIR/fake_model.py" "$PORT" > "$RUN/fake_model.log" 2>&1 &
echo $! > "$RUN/fake_model.pid"
for _ in $(seq 50); do
  curl -sf "http://127.0.0.1:$PORT/v1/models" > /dev/null && break
  sleep 0.1
done
curl -sf "http://127.0.0.1:$PORT/v1/models" > /dev/null || { echo "デモ用ダミーモデルが起動しませんでした"; exit 1; }

# 2. Plugin from this checkout.
rsync -a --exclude .git --exclude __pycache__ --exclude tests --exclude demo \
  "$REPO/" "$HOME_DIR/plugins/cron-budget/"

# 3. Config pointing every model call at the demo dummy model.
cat > "$HOME_DIR/config.yaml" <<YAML
model:
  default: demo-dummy-model
  provider: custom
  base_url: http://127.0.0.1:$PORT/v1
  api_key: fake
plugins:
  enabled: [cron-budget]
memory:
  memory_enabled: false
  user_profile_enabled: false
YAML

# 4. Small budget, observe mode (scene 2 shows it recording without blocking).
cat > "$HOME_DIR/plugin-data/cron-budget/budget.json" <<JSON
{"mode": "observe", "daily_limit": $DAILY_LIMIT, "chat_reserve": $CHAT_RESERVE}
JSON

# 5. The noisy job from the story.
out="$(hermes cron create --name "$JOB_NAME" --deliver local "*/5 * * * *" "Summarize today's news in 3 lines" 2>&1)"
job="$(printf '%s\n' "$out" | grep -oE '\b[0-9a-f]{12}\b' | head -1)"
[ -n "$job" ] || { echo "cronジョブを作れませんでした:"; echo "$out"; exit 1; }
echo "$job" > "$RUN/job_id"
echo "$JOB_NAME" > "$RUN/job_name"
# Paused, so the gateway's 60-second ticker never fires it on its own while filming.
# demo/run-cron.sh still runs it by hand.
hermes cron pause "$job" > /dev/null

cat <<EOF

✅ 練習用の環境ができました（いつもの ~/.hermes には触れていません）
   HERMES_HOME : $HOME_DIR
   ダミーモデル : http://127.0.0.1:$PORT/v1
   上限         : 1日 $DAILY_LIMIT 回、チャット用に $CHAT_RESERVE 回（cronは $((DAILY_LIMIT - CHAT_RESERVE)) 回まで）
   ジョブ       : $JOB_NAME ($job) — 5分おき（自動では動かないよう一時停止中）

次の手順:
  ターミナルで   source demo/env.sh       # このターミナルの hermes を練習用に切り替え
  横のペインで   tail -f demo/.run/fake_model.log   # モデルに届いた呼び出しが見える
  状態を見る     hermes cron-budget status           # チャット中なら /cron-budget
  止める設定     hermes cron-budget set mode enforce
  cronを動かす   demo/run-cron.sh                    # 押すたびに1回
  チャット       hermes chat
  片付け         demo/stop.sh
EOF
