#!/usr/bin/env python3
"""Demo dummy model: an OpenAI-compatible server for the demo. It answers instantly and never contacts a
real provider, so no quota is spent. Every request it receives is printed, numbered, so you can
watch which runs actually reached "the model". Usage: python3 fake_model.py [port]"""
import http.server
import json
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18765
COUNT = 0
NEWS = "Here are today's top 3 headlines. (demo dummy model)"
CHAT = "Good morning! How can I help you today? (demo dummy model)"


def answer_for(request):
    """Cron's news prompt gets headlines; anything else gets a chat greeting."""
    last = next((m for m in reversed(request.get("messages") or []) if m.get("role") == "user"), {})
    content = last.get("content")
    text = content if isinstance(content, str) else json.dumps(content)
    return NEWS if "news" in text.lower() else CHAT


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json({"data": [{"id": "demo-dummy-model", "context_length": 200000}]})

    def do_POST(self):
        global COUNT
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        COUNT += 1
        print(f"{time.strftime('%H:%M:%S')}  📨 model request #{COUNT}", flush=True)
        ANSWER = answer_for(request)
        message = {"role": "assistant", "content": ANSWER}
        if request.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            base = {"id": "x", "object": "chat.completion.chunk", "created": 1, "model": "demo-dummy-model"}
            for delta, finish in (({"role": "assistant", "content": ANSWER}, None), ({}, "stop")):
                chunk = dict(base, choices=[{"index": 0, "delta": delta, "finish_reason": finish}])
                self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return
        self._json({"id": "x", "object": "chat.completion", "created": 1, "model": "demo-dummy-model",
                    "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


if __name__ == "__main__":
    print(f"demo dummy model: http://127.0.0.1:{PORT}/v1  (never contacts a real provider)", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Fake).serve_forever()
