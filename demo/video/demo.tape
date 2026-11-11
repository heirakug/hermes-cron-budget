# cron-budget demo video (~80s). Render with demo/video/render.sh, which builds the practice
# environment (demo/start.sh) first and cleans it up afterwards: demo dummy model, no real quota.
# Captions live in helpers.sh (VHS cannot type Japanese); this file types ASCII only.

Output demo/video/cron-budget-demo.mp4

Set Shell "bash"
Set FontFamily "Menlo, Hiragino Sans, Hiragino Kaku Gothic ProN"
Set FontSize 24
Set Width 1400
Set Height 800
Set Padding 36
Set Theme "Catppuccin Mocha"
Set TypingSpeed 30ms
Set WaitPattern /^\$ ?$/
Set WaitTimeout 60s

# --- setup (not recorded) ---
Hide
Type "source demo/env.sh && source demo/video/helpers.sh && clear"
Enter
Wait
Show

# --- 1. The problem (~9s) ---
Hide
Type "c1"
Enter
Wait
Show
Sleep 5s
Hide
Type "c2"
Enter
Wait
Show
Sleep 2500ms

# --- 2. Installed, observe mode (~9s) ---
Hide
Type "c3"
Enter
Wait
Show
Sleep 1s
Type "hermes cron-budget status"
Enter
Wait
Sleep 7s

# --- 3. Held (~33s) ---
Hide
Type "c4"
Enter
Wait
Show
Sleep 1500ms
Type "hermes cron-budget set mode enforce"
Enter
Wait
Sleep 5s

Hide
Type "c5"
Enter
Wait
Show
Sleep 1s
Type "demo/run-cron.sh"
Enter
Wait
Type "demo/run-cron.sh"
Enter
Wait
Type "demo/run-cron.sh"
Enter
Wait
Type "demo/run-cron.sh"
Enter
Wait
Type "demo/run-cron.sh"
Enter
Wait
Type "demo/run-cron.sh"
Enter
Wait
Sleep 700ms

Hide
Type "c6"
Enter
Wait
Show
Sleep 1s
Type "demo/run-cron.sh"
Enter
Wait
Sleep 3s

Hide
Type "c7"
Enter
Wait
Show
Sleep 1s
Type "demo/run-cron.sh"
Enter
Wait
Sleep 1500ms

# --- 4. Chat still works (~10s) ---
Hide
Type "c8"
Enter
Wait
Show
Sleep 1s
Type `hermes chat -Q -q "Good morning!" 2>/dev/null | head -1`
Enter
Wait
Sleep 3s

# --- 5. Wrap-up (~12s) ---
Hide
Type "c9"
Enter
Wait
Show
Sleep 700ms
Type "hermes cron-budget status"
Enter
Wait
Sleep 7s
Hide
Type "c10"
Enter
Wait
Show
Sleep 5s
