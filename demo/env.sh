# Source this in a terminal to point `hermes` at the practice environment:
#   source demo/env.sh
# Your usual ~/.hermes is not touched. Open a new terminal (or run `exit`) to go back.
DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")" && pwd)"
export HERMES_HOME="$DEMO_DIR/.run/home"
export HERMES_ACCEPT_HOOKS=1
# Run hermes with only the variables it needs, so no real provider key reaches the practice
# environment (nothing else from your shell is passed through).
hermes() {
  env -i HOME="$HOME" PATH="$PATH" TERM="${TERM:-dumb}" LANG="${LANG:-en_US.UTF-8}" \
    LC_ALL="${LC_ALL:-}" HERMES_HOME="$HERMES_HOME" HERMES_ACCEPT_HOOKS=1 OPENAI_API_KEY=fake \
    command hermes "$@"
}
case "$-" in *i*) [ -z "${DEMO_PROMPT_SET:-}" ] && PS1="(demo) ${PS1:-}" && DEMO_PROMPT_SET=1 ;; esac
