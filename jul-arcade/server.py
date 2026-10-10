"""JuL Arcade: serves the game page and plays the player's machine with the real model.

    python server.py                                   # JuL in-process (jul-decision-e5-small)
    python server.py --url http://127.0.0.1:8577       # any System One server (jul serve, Lambda, Jev)

Routes: GET / (the game), GET /api/levels, POST /api/play {"level": id, "machine": {...}}.
Standard library only. Binds to 127.0.0.1.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from engine import HttpBrain, LocalBrain, MachineError, play

HERE = Path(__file__).parent
LEVELS = json.loads((HERE / "levels.json").read_text())["levels"]
BY_ID = {l["id"]: l for l in LEVELS}
_lock = threading.Lock()
brain = None


def public_level(l: dict) -> dict:
    """What the browser gets: no answers for the wave (it learns them after playing)."""
    return {k: l[k] for k in ("id", "title", "brief", "tools", "portals", "starter", "examples")} | {
        "wave_size": len(l["wave"])}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            self._send(200, (HERE / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif p == "/api/levels":
            self._send(200, {"levels": [public_level(l) for l in LEVELS], "brain": brain.name})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/play":
            return self._send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            level = BY_ID[body["level"]]
            t = time.time()
            with _lock:
                res = play(brain, level, body["machine"])
            res["wall_s"] = round(time.time() - t, 2)
            print(f"[play] {level['id']}: {res['correct']}/{res['total']} {'★' * res['stars']} "
                  f"{res['calls']} calls {res['ms_per_call']} ms/call", flush=True)
            self._send(200, res)
        except MachineError as e:
            self._send(400, {"error": str(e)})
        except KeyError as e:
            self._send(400, {"error": f"champ manquant : {e}"})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="jul-decision-e5-small")
    ap.add_argument("--backend", default=None)
    ap.add_argument("--url", default=None, help="a System One server instead of in-process JuL")
    ap.add_argument("--port", type=int, default=8600)
    a = ap.parse_args()
    brain = HttpBrain(a.url) if a.url else LocalBrain(a.model, a.backend)
    t = time.time()
    brain.ask("warmup", {"type": "choice", "instructions": "", "criteria": {"a": None, "b": None}})
    print(f"brain ready: {brain.name} ({time.time() - t:.1f}s) -> http://127.0.0.1:{a.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
