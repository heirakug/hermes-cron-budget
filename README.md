# cron-budget

Keep scheduled jobs from spending the requests people need for chat.

Free tiers cost $0 and still run out. A cron job that runs every five minutes can use up a
provider's daily request quota before anyone opens a chat, and then every profile on the
machine stops working until the quota window resets. cron-budget counts **provider requests,
not dollars**, across every profile on the machine, and holds cron jobs once they reach the
part of the quota kept for chat.

## How it works

- Every model call goes through one `llm_execution` middleware. Calls are recorded in a
  ledger shared by all profiles, since profiles on one provider key share one quota.
- Auxiliary calls (titling, compression and the like) are counted through the
  `pre_auxiliary_call` hook. They are never blocked.
- Cron calls stop at `daily_limit - chat_reserve`. **Chat is never blocked.**
- A held job returns a synthetic final answer instead of calling the provider. The first
  run in a window reports why it was held, and later runs reply `[SILENT]`, so a held job
  does not flood your messages. Nothing reaches the provider until the window resets.
- An optional `job_limit` caps a single job per window.
- If accounting itself fails, the call goes through and `status` shows a warning. A budget
  plugin must never be the reason an agent stops working.

## Install

```bash
hermes plugins install heirakug/hermes-cron-budget
```

Requires Hermes `>=0.22.1`.

## Use

It starts in **observe** mode: it records what it would have blocked and blocks nothing.

```bash
hermes cron-budget status                  # or /cron-budget in chat
hermes cron-budget set daily_limit 1000    # your provider's requests per window
hermes cron-budget set chat_reserve 300    # kept for people
hermes cron-budget set reset 09:00         # local time the provider's window reopens
hermes cron-budget set timezone Asia/Tokyo
hermes cron-budget set models "*:free"     # only count these models (globs, comma separated)
hermes cron-budget set job_limit 50        # optional per-job cap; "off" to clear
hermes cron-budget set mode enforce        # start holding jobs
```

`status` shows the window, requests used by cron, chat and auxiliary calls, and each job's
requests, blocked runs and would-block runs.

| Setting | Default | Meaning |
|---|---|---|
| `mode` | `observe` | `observe` records, `enforce` holds jobs |
| `daily_limit` | `1000` | provider requests per window, all profiles together |
| `chat_reserve` | `300` | requests kept for chat |
| `job_limit` | none | optional cap for one job per window |
| `reset` | `00:00` | local time the window reopens |
| `timezone` | machine zone | IANA zone name |
| `models` | `["*"]` | model name globs that count |

## Disclosure

- Registers one `llm_execution` middleware, one `pre_auxiliary_call` hook, the
  `hermes cron-budget` CLI command and the `/cron-budget` slash command.
- Stores request counts with timestamps, profile, job ids and names, provider and model names
  in `plugin-data/cron-budget/` under the root Hermes home (SQLite ledger and `budget.json`).
  **Never message text.**
- No network calls, no credentials, no shell commands, no background processes, no telemetry.
- Does not write the cron store: jobs keep their schedules and resume on their own when the
  window resets.
- Only `chat_completions` calls are held. Other API modes are recorded as would-block and
  allowed.

## Tests

```bash
python3 tests/test_core.py          # ledger and policy
python tests/e2e_real_hermes.py     # real hermes + fake provider, no quota used
python tests/e2e_edge_cases.py
```

The end-to-end tests need Hermes installed and run against a local fake provider.

## License

MIT
