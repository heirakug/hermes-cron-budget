#!/usr/bin/env python3
"""End to end: the real `hermes` binary, a temporary HERMES_HOME and a fake model server. No real
provider is contacted and no quota is spent. Usage: python3 tests/e2e_real_hermes.py"""
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HITS = []


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        body = b'{"data":[{"id":"fake-model","context_length":200000}]}'
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        HITS.append(self.path)
        message = {"role": "assistant", "content": "REAL MODEL ANSWER"}
        if request.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            base = {"id": "x", "object": "chat.completion.chunk", "created": 1, "model": "fake-model"}
            for delta, finish in (({"role": "assistant", "content": message["content"]}, None), ({}, "stop")):
                chunk = dict(base, choices=[{"index": 0, "delta": delta, "finish_reason": finish}])
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return
        body = json.dumps({"id": "x", "object": "chat.completion", "created": 1, "model": "fake-model",
                           "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    home = Path(tempfile.mkdtemp(prefix="cron-budget-e2e-"))
    failures = []

    def check(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
        if not ok:
            failures.append(name)

    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env.update(HERMES_HOME=str(home), HERMES_ACCEPT_HOOKS="1", OPENAI_API_KEY="fake", NO_COLOR="1")

    def hermes(*args, timeout=180):
        result = subprocess.run(["hermes", *args], env=env, text=True, capture_output=True, timeout=timeout)
        return result.stdout + result.stderr

    try:
        (home / "plugins").mkdir()
        shutil.copytree(REPO, home / "plugins" / "cron-budget",
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "tests"))
        (home / "config.yaml").write_text(
            "model:\n  default: fake-model\n  provider: custom\n"
            f"  base_url: http://127.0.0.1:{server.server_port}/v1\n  api_key: fake\n"
            "plugins:\n  enabled: [cron-budget]\n"
            "memory:\n  memory_enabled: false\n  user_profile_enabled: false\n")
        data = home / "plugin-data" / "cron-budget"
        data.mkdir(parents=True)
        (data / "budget.json").write_text('{"mode": "enforce", "daily_limit": 3, "chat_reserve": 1}')
        print(hermes("plugins", "list")[:900])

        output = hermes("cron", "create", "--name", "noisy", "--deliver", "local", "0 7 * * *", "say hi")
        job = next((w for w in output.split() if len(w) == 12 and all(c in "0123456789abcdef" for c in w)), "")
        check("job created", bool(job), job)

        def run():
            before = set((home / "cron" / "output" / job).glob("*.md")) if (home / "cron" / "output" / job).exists() else set()
            ran = hermes("cron", "run", job)
            new = sorted(set((home / "cron" / "output" / job).glob("*.md")) - before)
            return ran, (new[-1].read_text().split("## Response")[-1] if new else "")

        for number in (1, 2):
            ran, report = run()
            check(f"run {number} reaches the model", "REAL MODEL ANSWER" in report and len(HITS) == number,
                  f"hits={len(HITS)}")
        hits = len(HITS)
        ran, report = run()
        check("run 3 is held with a notice", "cron-budget held" in report, report[-160:].replace("\n", " "))
        check("run 3 made no model call", len(HITS) == hits, f"hits={len(HITS)}")
        check("held run is not a failure", "succeeded" in ran.lower(), ran[-120:].replace("\n", " "))
        ran, report = run()
        check("run 4 is silent", "[SILENT]" in report, report[-100:].replace("\n", " "))
        check("run 4 made no model call", len(HITS) == hits, f"hits={len(HITS)}")

        chat = hermes("chat", "-q", "hello", "-Q")
        check("chat still reaches the model", len(HITS) > hits and "REAL MODEL ANSWER" in chat,
              f"hits={len(HITS)} {chat[-80:]!r}")
        status = hermes("cron-budget", "status")
        check("status command works", "mode: enforce" in status and "noisy" in status, status.replace("\n", " | ")[:300])
        print(status)
    finally:
        server.shutdown()
        shutil.rmtree(home, ignore_errors=True)
    print(f"\n{'ALL PASSED' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
