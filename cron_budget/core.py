"""Request ledger and budget policy. Standard library only: plugins may run in a separate host."""
from __future__ import annotations

import fnmatch
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

DEFAULTS: dict[str, Any] = {
    "mode": "observe",        # observe: record what would be blocked. enforce: block it.
    "daily_limit": 1000,      # provider requests per window, across every profile
    "chat_reserve": 300,      # kept for people: cron stops at daily_limit - chat_reserve
    "job_limit": None,        # optional cap for one job per window
    "reset": "00:00",         # local time the provider's window reopens
    "timezone": None,         # IANA name; None uses the machine's zone
    "models": ["*"],          # model name globs that count, e.g. ["*:free"]
}


def data_dir() -> Path:
    """Shared by every profile: profiles on one provider key share one quota."""
    from hermes_constants import get_default_hermes_root

    path = Path(get_default_hermes_root()) / "plugin-data" / "cron-budget"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config(directory: Optional[Path] = None) -> dict[str, Any]:
    path = (directory or data_dir()) / "budget.json"
    config = dict(DEFAULTS)
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            config.update({k: v for k, v in loaded.items() if k in DEFAULTS})
    return config


def save_config(config: dict[str, Any], directory: Optional[Path] = None) -> None:
    path = (directory or data_dir()) / "budget.json"
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def window_bounds(config: dict[str, Any], now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Start and end of the quota window containing ``now``."""
    zone = ZoneInfo(config["timezone"]) if config.get("timezone") else None
    current = now.astimezone(zone) if now else datetime.now(zone).astimezone(zone)
    hour, minute = (int(part) for part in str(config["reset"]).split(":"))
    start = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if current < start:
        start -= timedelta(days=1)
    return start, start + timedelta(days=1)


def model_counts(model: Optional[str], config: dict[str, Any]) -> bool:
    return any(fnmatch.fnmatch(model or "", glob) for glob in config.get("models") or ["*"])


@dataclass(frozen=True)
class Decision:
    block: bool
    reason: Optional[str]  # None, "chat_reserve" or "job_limit"
    used: int
    job_used: int
    cron_cap: int


class Ledger:
    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = directory or data_dir()
        self.path = self.directory / "ledger.db"
        with self._connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS calls (
                    ts REAL NOT NULL, kind TEXT NOT NULL, verdict TEXT NOT NULL,
                    profile TEXT, job_id TEXT, job_name TEXT, provider TEXT, model TEXT,
                    counted INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS calls_ts ON calls(ts);
                CREATE TABLE IF NOT EXISTS notices (
                    window_start REAL NOT NULL, job_id TEXT NOT NULL, reason TEXT NOT NULL,
                    PRIMARY KEY (window_start, job_id));
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def record(self, *, kind: str, verdict: str, counted: bool, profile: str = "",
               job_id: Optional[str] = None, job_name: Optional[str] = None,
               provider: Optional[str] = None, model: Optional[str] = None,
               ts: Optional[float] = None) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?)",
                (ts if ts is not None else time.time(), kind, verdict, profile, job_id, job_name,
                 provider, model, int(counted)),
            )

    def used(self, start: datetime, end: datetime, job_id: Optional[str] = None) -> int:
        """Requests that reached a provider in this window; blocked ones cost nothing."""
        query = ("SELECT COUNT(*) FROM calls WHERE ts >= ? AND ts < ? AND counted = 1 "
                 "AND verdict != 'blocked'")
        args: list[Any] = [start.timestamp(), end.timestamp()]
        if job_id is not None:
            query += " AND job_id = ?"
            args.append(job_id)
        with self._connect() as db:
            return int(db.execute(query, args).fetchone()[0])

    def decide(self, config: dict[str, Any], job_id: Optional[str],
               now: Optional[datetime] = None) -> Decision:
        start, end = window_bounds(config, now)
        used = self.used(start, end)
        job_used = self.used(start, end, job_id) if job_id else 0
        cap = max(0, int(config["daily_limit"]) - int(config["chat_reserve"]))
        reason = None
        if used >= cap:
            reason = "chat_reserve"
        elif config.get("job_limit") is not None and job_used >= int(config["job_limit"]):
            reason = "job_limit"
        return Decision(reason is not None, reason, used, job_used, cap)

    def first_notice(self, config: dict[str, Any], job_id: str, reason: str,
                     now: Optional[datetime] = None) -> bool:
        """True once per job per window, so a held job reports once and then stays quiet."""
        start, _ = window_bounds(config, now)
        with self._connect() as db:
            cursor = db.execute("INSERT OR IGNORE INTO notices VALUES (?,?,?)",
                                (start.timestamp(), job_id, reason))
            return cursor.rowcount == 1

    def summary(self, config: dict[str, Any], now: Optional[datetime] = None) -> dict[str, Any]:
        start, end = window_bounds(config, now)
        args = (start.timestamp(), end.timestamp())
        with self._connect() as db:
            kinds = dict(db.execute(
                "SELECT kind, COUNT(*) FROM calls WHERE ts >= ? AND ts < ? AND counted = 1 "
                "AND verdict != 'blocked' GROUP BY kind", args).fetchall())
            jobs = db.execute(
                "SELECT profile, COALESCE(job_name, job_id), "
                "SUM(verdict != 'blocked'), SUM(verdict = 'blocked'), SUM(verdict = 'would_block') "
                "FROM calls WHERE ts >= ? AND ts < ? AND counted = 1 AND job_id IS NOT NULL "
                "GROUP BY profile, job_id ORDER BY 3 DESC, 4 DESC", args).fetchall()
        return {"start": start, "end": end, "kinds": kinds, "jobs": jobs,
                "used": self.used(start, end)}
