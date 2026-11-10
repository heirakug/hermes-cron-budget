#!/usr/bin/env python3
"""Edge cases with the real binary and a fake server: a second profile, the scheduler path, retries
after 429, and plugins.isolation: host. Usage: python3 tests/e2e_edge_cases.py"""
import http.server
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HITS, STATUS = [], {"code": 200}


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        self._send(200, {"data": [{"id": "fake-model", "context_length": 200000}]})

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        HITS.append(self.path)
        if STATUS["code"] != 200:
            return self._send(STATUS["code"], {"error": {"message": "rate limited", "code": STATUS["code"]}})
        if request.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            base = {"id": "x", "object": "chat.completion.chunk", "created": 1, "model": "fake-model"}
            for delta, finish in (({"role": "assistant", "content": "OK"}, None), ({}, "stop")):
                self.wfile.write(f"data: {json.dumps(dict(base, choices=[{'index': 0, 'delta': delta, 'finish_reason': finish}]))}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return
        self._send(200, {"id": "x", "object": "chat.completion", "created": 1, "model": "fake-model",
                         "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    home = Path(tempfile.mkdtemp(prefix="cron-budget-edge-"))
    failures = []

    def check(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
        if not ok:
            failures.append(name)

    base_env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    base_env.update(HERMES_ACCEPT_HOOKS="1", OPENAI_API_KEY="fake", NO_COLOR="1")

    def hermes(hermes_home, *args, timeout=240):
        env = dict(base_env, HERMES_HOME=str(hermes_home))
        result = subprocess.run(["hermes", *args], env=env, text=True, capture_output=True, timeout=timeout)
        return result.stdout + result.stderr

    def job_id(output):
        return next((w for w in output.split() if len(w) == 12 and all(c in "0123456789abcdef" for c in w)), "")

    def prepare(target, extra=""):
        target.mkdir(parents=True, exist_ok=True)
        (target / "plugins").mkdir(exist_ok=True)
        shutil.copytree(REPO, target / "plugins" / "cron-budget", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "tests"))
        (target / "config.yaml").write_text(
            "model:\n  default: fake-model\n  provider: custom\n"
            f"  base_url: http://127.0.0.1:{server.server_port}/v1\n  api_key: fake\n"
            f"plugins:\n  enabled: [cron-budget]\n{extra}"
            "memory:\n  memory_enabled: false\n  user_profile_enabled: false\n")

    def budget(**values):
        data = home / "plugin-data" / "cron-budget"
        data.mkdir(parents=True, exist_ok=True)
        (data / "budget.json").write_text(json.dumps(values))
        db = data / "ledger.db"
        if db.exists():
            with sqlite3.connect(db) as connection:
                connection.execute("DELETE FROM calls")
                connection.execute("DELETE FROM notices")

    try:
        prepare(home)
        second = home / "profiles" / "second"
        prepare(second)

        # 1. A request from one profile counts against a job in another.
        budget(mode="enforce", daily_limit=2, chat_reserve=0)
        first_job = job_id(hermes(home, "cron", "create", "--name", "root-job", "--deliver", "local", "0 7 * * *", "hi"))
        second_job = job_id(hermes(second, "cron", "create", "--name", "second-job", "--deliver", "local", "0 7 * * *", "hi"))
        for _ in range(2):
            hermes(home, "cron", "run", first_job)
        hits = len(HITS)
        hermes(second, "cron", "run", second_job)
        check("second profile shares the budget", len(HITS) == hits and hits == 2, f"hits={len(HITS)}")
        status = hermes(second, "cron-budget", "status")
        check("one ledger is visible from both", "root-job" in status and "second-job" in status,
              status.replace("\n", " | ")[:260])

        # 2. Scheduler path, not a manual run: the job must be recognised as cron.
        budget(mode="enforce", daily_limit=1, chat_reserve=0)
        HITS.clear()
        hermes(home, "cron", "run", first_job)
        hits = len(HITS)
        hermes(home, "cron", "edit", first_job, "--schedule", "every 1m")
        jobs_path = home / "cron" / "jobs.json"
        data = json.loads(jobs_path.read_text())
        for job in data.get("jobs", data):
            if job["id"] == first_job:
                job["next_run_at"] = "2020-01-01T00:00:00+00:00"
        jobs_path.write_text(json.dumps(data))
        tick = hermes(home, "cron", "tick")
        check("scheduler tick is held too", len(HITS) == hits, f"hits={len(HITS)} {tick[-100:]!r}")

        # 3. Retries are physical requests and must count.
        budget(mode="observe", daily_limit=1000, chat_reserve=0)
        HITS.clear()
        STATUS["code"] = 429
        hermes(home, "cron", "edit", first_job, "--schedule", "0 7 * * *")
        hermes(home, "cron", "run", first_job, timeout=300)
        STATUS["code"] = 200
        counted = hermes(home, "cron-budget", "status")
        used = int(counted.split("used: ")[1].split(" ")[0])
        check("every retry is counted", used == len(HITS) and used > 1, f"counted={used} server={len(HITS)}")

        # 4. plugins.isolation: host — the plugin runs in another process.
        isolated = home / "profiles" / "isolated"
        prepare(isolated, "  isolation: host\n")
        budget(mode="enforce", daily_limit=1, chat_reserve=0)
        HITS.clear()
        host_job = job_id(hermes(isolated, "cron", "create", "--name", "host-job", "--deliver", "local", "0 7 * * *", "hi"))
        for _ in range(2):
            ran = hermes(isolated, "cron", "run", host_job)
        status = hermes(isolated, "cron-budget", "status")
        print("isolation host: hits", len(HITS), "|", status.replace("\n", " | ")[:280])
        check("host isolation holds the second run", len(HITS) == 1, f"hits={len(HITS)}")
    finally:
        server.shutdown()
        shutil.rmtree(home, ignore_errors=True)
    print(f"\n{'ALL PASSED' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
