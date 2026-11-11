# Helpers sourced (hidden) by demo.tape. VHS cannot type Japanese reliably, so every caption
# lives here and the tape only types short ASCII names (c1, c2 ...).
# Captions are English first, with the Japanese line right under each one.
PS1='$ '
export LC_ALL=en_US.UTF-8

# Full-screen title card: card "English" "日本語" "English" "日本語" ...
card() {
  clear
  printf '\n\n'
  while [ $# -gt 0 ]; do
    printf '    \e[1;33m%s\e[0m\n' "$1"
    printf '    \e[2m%s\e[0m\n\n' "${2:-}"
    shift 2 || shift
  done
}

# Caption at the top of a scene: scene "English" "日本語" ["English detail" "日本語の補足"]
scene() {
  clear
  printf '\e[1;36m▍ %s\e[0m\n' "$1"
  printf '\e[2;36m  %s\e[0m\n' "${2:-}"
  if [ -n "${3:-}" ]; then
    printf '  \e[0;37m%s\e[0m\n' "$3"
    printf '\e[2m  %s\e[0m\n' "${4:-}"
  fi
  printf '\n'
}

c1() { card "The free tier allows 1,000 requests a day." "無料枠は1日1000回。" \
            "A cron job every 5 minutes used them all up," "5分おきのcronが枠を使い切り、" \
            "and by morning, chat had stopped working." "朝にはチャットが止まっていた。"; }
c2() { card "cron-budget: hold cron jobs, keep chat's share." "cron-budget：cronだけを止めて、チャットの分は残す。"; }
c3() { scene "Installed: observe mode first" "入れたところ：まずは観察モード" \
             "Nothing is blocked, requests are only counted" "止めずに、回数を記録するだけ"; }
c4() { scene "A small budget, so it's easy to see" "見やすいように上限を小さく" \
             "10 a day, 4 kept for chat → cron gets 6" "1日10回、チャット用に4回 → cronは6回まで"; }
c5() { scene "Run the cron job" "cronを動かしてみる" \
             "The first 6 runs work as usual" "6回までは普通に動く"; }
c6() { scene "Run 7: held" "7回目：止まる" \
             "One notice, sent only once" "「止めました」の通知が1回だけ出る"; }
c7() { scene "Run 8 and after: silent" "8回目から：何も言わずに休む" \
             "No request reaches the model" "モデルには1回も届かない"; }
c8() { scene "Cron is held, but chat still answers" "cronは止まっても、チャットには返事が来る"; }
c9() { scene "Requests per job" "ジョブごとの回数"; }
c10() { card "✓ Counts requests, not dollars" "ドルではなく、回数で数える" \
             "✓ Shared across every profile" "全プロファイルで共有" \
             "✓ If it breaks, it lets calls through" "壊れても止めない"; }
