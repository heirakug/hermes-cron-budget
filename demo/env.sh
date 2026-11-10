# Source this in a terminal to point `hermes` at the practice environment:
#   source demo/env.sh
# Your usual ~/.hermes is not touched. Open a new terminal (or run `exit`) to go back.
DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")" && pwd)"
export HERMES_HOME="$DEMO_DIR/.run/home"
export HERMES_ACCEPT_HOOKS=1
export OPENAI_API_KEY=fake
# Make sure no real provider key leaks into the practice environment.
for var in $(env | sed -n 's/^\([A-Z0-9_]*_API_KEY\)=.*/\1/p'); do
  [ "$var" = OPENAI_API_KEY ] || unset "$var"
done
case "$-" in *i*) [ -z "${DEMO_PROMPT_SET:-}" ] && PS1="(demo) ${PS1:-}" && DEMO_PROMPT_SET=1 ;; esac
