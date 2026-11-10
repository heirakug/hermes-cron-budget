"""`hermes cron-budget` and `/cron-budget`."""
from __future__ import annotations

import argparse
from typing import Any

from .core import DEFAULTS, Ledger, load_config, save_config, window_bounds

HELP = "Keep scheduled jobs from spending the request quota people need for chat"


def render_status() -> str:
    ledger = Ledger()
    config = load_config(ledger.directory)
    data = ledger.summary(config)
    cap = max(0, int(config["daily_limit"]) - int(config["chat_reserve"]))
    kinds = data["kinds"]
    lines = [
        f"mode: {config['mode']}",
        f"window: {data['start']:%m-%d %H:%M} to {data['end']:%m-%d %H:%M %Z}",
        f"used: {data['used']} / {config['daily_limit']} "
        f"(cron stops at {cap}, {config['chat_reserve']} kept for chat)",
        f"by kind: cron {kinds.get('cron', 0)}, chat {kinds.get('chat', 0)}, "
        f"auxiliary {kinds.get('aux', 0)}",
    ]
    if data["jobs"]:
        lines.append("jobs (requests / blocked / would block):")
        lines += [f"  {profile}/{name}: {sent} / {blocked} / {would}"
                  for profile, name, sent, blocked, would in data["jobs"]]
    else:
        lines.append("jobs: none in this window")
    failure = ledger.directory / "last_failure"
    if failure.exists():
        lines.append(f"warning: at {failure.read_text()} a call could not be counted and was allowed through")
    return "\n".join(lines)


def setup(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("status", help="Show the current window")
    setter = sub.add_parser("set", help="Change a setting")
    setter.add_argument("key", choices=sorted(DEFAULTS))
    setter.add_argument("value")


def _parse(key: str, value: str) -> Any:
    if key in {"daily_limit", "chat_reserve"}:
        return int(value)
    if key == "job_limit":
        return None if value.lower() in {"none", "off"} else int(value)
    if key == "mode":
        if value not in {"observe", "enforce"}:
            raise ValueError("mode must be observe or enforce")
    if key == "models":
        return [part.strip() for part in value.split(",") if part.strip()]
    if key == "timezone" and value.lower() == "none":
        return None
    return value


def handle(args: argparse.Namespace) -> int:
    if getattr(args, "action", None) == "set":
        directory = Ledger().directory
        config = load_config(directory)
        try:
            config[args.key] = _parse(args.key, args.value)
            window_bounds(config)
        except Exception as exc:  # a bad value must not reach the file the gate reads
            print(f"Not saved: {exc}")
            return 2
        save_config(config, directory)
    print(render_status())
    return 0


def slash(_raw_args: str = "") -> str:
    return render_status()
