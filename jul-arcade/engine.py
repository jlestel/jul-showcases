"""The game's rules: run a player's decision machine over a level's wave, with JuL as the brain.

A machine is a small tree. Each node is one typed decision, the same shape as a Jev/JuL question,
plus where each answer goes (a portal id, or another node):

    {"type": "choice", "instructions": "...", "options": [{"key": "a", "description": "...", "to": <dest>}]}
    {"type": "noul",   "instructions": "...", "yes": <dest>, "no": <dest>, "threshold": 0.5}
    {"type": "score",  "instructions": "...", "levels": ["lowest", ..., "highest"],
                       "threshold": 0.5, "above": <dest>, "below": <dest>}

<dest> is a portal id (str) or a nested node (dict). Nothing here knows any level: levels live in
levels.json. Every decision is a real call, either in-process (`TypeSafeClient`) or to any server
speaking the System One protocol (`jul serve`, a Lambda, Jev).
"""

from __future__ import annotations

import json
import time
import urllib.request

MAX_DEPTH = 4


class MachineError(ValueError):
    pass


def to_wire(node: dict) -> dict:
    """The node as a Jev/JuL HTTP question (what the player sees as 'the API call')."""
    kind = node.get("type")
    instr = (node.get("instructions") or "").strip()
    if kind == "choice":
        opts = node.get("options") or []
        if len(opts) < 2:
            raise MachineError("Un Choice a besoin d'au moins 2 options.")
        crit = {}
        for o in opts:
            key = (o.get("key") or "").strip()
            if not key:
                raise MachineError("Chaque option d'un Choice a besoin d'un nom.")
            if key in crit:
                raise MachineError(f"Deux options s'appellent « {key} ».")
            crit[key] = (o.get("description") or "").strip() or None
        return {"type": "choice", "instructions": instr, "criteria": crit}
    if kind == "noul":
        if not instr:
            raise MachineError("Un Noul a besoin d'une question oui/non.")
        return {"type": "noul", "instructions": instr}
    if kind == "score":
        levels = [l.strip() for l in node.get("levels") or [] if l and l.strip()]
        if len(levels) < 2:
            raise MachineError("Un Score a besoin d'au moins 2 niveaux, du plus bas au plus haut.")
        return {"type": "score", "instructions": instr, "criteria": levels}
    raise MachineError(f"Type de décision inconnu : {kind!r}")


def validate(node, portals: set, depth: int = 0) -> int:
    """Check the tree (every branch ends on a portal); returns the number of decision nodes."""
    if isinstance(node, str):
        if node not in portals:
            raise MachineError(f"Une sortie mène nulle part (« {node or 'vide'} »).")
        return 0
    if not isinstance(node, dict):
        raise MachineError("Machine illisible.")
    if depth >= MAX_DEPTH:
        raise MachineError(f"Pas plus de {MAX_DEPTH} décisions en chaîne.")
    to_wire(node)
    kids = branches(node)
    return 1 + sum(validate(k, portals, depth + 1) for k in kids)


def branches(node: dict) -> list:
    if node["type"] == "choice":
        return [o.get("to") for o in node["options"]]
    if node["type"] == "noul":
        return [node.get("yes"), node.get("no")]
    return [node.get("above"), node.get("below")]


class LocalBrain:
    """JuL in-process."""

    def __init__(self, model: str, backend: str | None = None):
        from jul import TypeSafeClient
        self.client = TypeSafeClient(model=model, backend=backend)
        self.name = f"{model} (local)"

    def ask(self, text: str, wire: dict) -> dict:
        from jul import Choice, Noul, Score
        kind, instr, crit = wire["type"], wire["instructions"], wire.get("criteria")
        q = (Choice(instructions=instr, criteria={k: v or "" for k, v in crit.items()}) if kind == "choice"
             else Noul(instructions=instr) if kind == "noul" else Score(instructions=instr, criteria=crit))
        return self.client.system_one(text, {"q": q}).as_dict()["answers"]["q"]


class HttpBrain:
    """Any System One server: `jul serve`, a Lambda function URL, Jev."""

    def __init__(self, url: str, key: str | None = None):
        self.url = url.rstrip("/") + ("" if url.rstrip("/").endswith("/v1/systemone") else "/v1/systemone")
        self.key = key
        self.name = f"System One @ {url}"

    def ask(self, text: str, wire: dict) -> dict:
        body = json.dumps({"state": text, "questions": {"q": wire}}).encode()
        req = urllib.request.Request(self.url, body, {"Content-Type": "application/json",
                                                      **({"Authorization": f"Bearer {self.key}"} if self.key else {})})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["answers"]["q"]


def route(brain, node, text: str, trace: list):
    """Follow the machine for one text; every step is one real decision."""
    while isinstance(node, dict):
        wire = to_wire(node)
        t = time.perf_counter()
        ans = brain.ask(text, wire)
        ms = (time.perf_counter() - t) * 1000
        step = {"type": node["type"], "ms": round(ms, 1), "answer": ans}
        if node["type"] == "choice":
            idx = [o["key"].strip() for o in node["options"]].index(ans["choice"])
            step.update(branch=ans["choice"], confidence=ans["confidence"])
            node = node["options"][idx]["to"]
        elif node["type"] == "noul":
            p, th = ans["noul"], float(node.get("threshold", 0.5))
            yes = p >= th
            step.update(branch="oui" if yes else "non", confidence=round(abs(p - th) / max(th, 1 - th), 3), value=p)
            node = node["yes"] if yes else node["no"]
        else:
            n = len(wire["criteria"]) - 1
            v = ans["score"] / n if n else 0.0          # 0..1 along the levels
            th = float(node.get("threshold", 0.5))
            up = v >= th
            step.update(branch="au-dessus" if up else "en dessous", confidence=ans["confidence"], value=round(v, 3))
            node = node["above"] if up else node["below"]
        trace.append(step)
    return node


def play(brain, level: dict, machine: dict) -> dict:
    portals = set(level["portals"])
    n_nodes = validate(machine, portals)
    items, calls, total_ms = [], 0, 0.0
    for it in level["wave"]:
        trace: list = []
        got = route(brain, machine, it["text"], trace)
        calls += len(trace)
        total_ms += sum(s["ms"] for s in trace)
        items.append({"text": it["text"], "expected": it["portal"], "got": got, "ok": got == it["portal"],
                      "steps": trace})
    ok = sum(i["ok"] for i in items)
    acc = ok / len(items)
    words = _words(machine)
    stars = 3 if acc >= 0.9 else 2 if acc >= 0.75 else 1 if acc >= 0.5 else 0
    score = round(1000 * acc) - 5 * max(0, words - 15) - 50 * max(0, n_nodes - 1)
    return {"items": items, "correct": ok, "total": len(items), "accuracy": round(acc, 3), "stars": stars,
            "score": max(score, 0), "words": words, "nodes": n_nodes, "calls": calls,
            "ms_total": round(total_ms, 1), "ms_per_call": round(total_ms / max(calls, 1), 1),
            "brain": brain.name, "tokens": 0, "cost_usd": 0}


def _words(node) -> int:
    if not isinstance(node, dict):
        return 0
    w = len((node.get("instructions") or "").split())
    if node["type"] == "choice":
        w += sum(len((o.get("description") or "").split()) for o in node["options"])
    if node["type"] == "score":
        w += sum(len(l.split()) for l in node.get("levels") or [])
    return w + sum(_words(k) for k in branches(node))
