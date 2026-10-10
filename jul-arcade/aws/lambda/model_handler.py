"""A JuL decision function: jul-decision-e5-small answering System One questions written by the player.

The game's questions are not known in advance, so there is no `jul pack` bundle here: the questions
come in the event, in the System One wire format, and are answered with the model in the package.

ROLE (env) says which reading this function carries (docs/aws-lambda.md, "one model per function"):
    choice : the vector model (model/), Choice questions. Each option set is compiled once, then cached
             while the instance stays warm.
    cross  : the cross model (model-cross/), Noul and Score questions. It reads question and text
             together on every call: nothing to compile.
    both   : the two models (the container image), every type.

Event:  {"state": "...", "questions": {"q": {"type": "choice", "instructions": "...", "criteria": {...}}}}
        {"warmup": true}  -> answers nothing, says how long the init took (the game pings it on load)
Result: {"answers": {"q": {...}}, "ms": 12.3, "role": "choice"}
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

T0 = time.perf_counter()
HERE = Path(__file__).resolve().parent
ROLE = os.environ.get("ROLE", "both")
MODEL = "jul-decision-e5-small"
VECTOR_DIR, CROSS_DIR = HERE / "model", HERE / "model-cross"

# The package is read-only: the preset goes to /tmp, pointed at the package's own model directories.
home = Path(os.environ.setdefault("JUL_HOME", "/tmp/jul_home"))
(home / "presets").mkdir(parents=True, exist_ok=True)
preset = json.loads((HERE / "preset" / f"{MODEL}@onnx.json").read_text())
preset["repos"] = {"onnx": str(VECTOR_DIR)}
if ROLE == "both":
    preset["cross"] = {"repo": str(CROSS_DIR), "subfolder": None}
(home / "presets" / f"{MODEL}@onnx.json").write_text(json.dumps(preset))
for center in (HERE / "preset").glob("*.center.npy"):
    shutil.copy(center, home / "presets")

from jul.client import _format  # noqa: E402  (after JUL_HOME is set)
from jul.types import Choice, Noul, Score, options_of  # noqa: E402

KINDS = {"choice": ("choice", "both"), "noul": ("cross", "both"), "score": ("cross", "both")}


def question(wire: dict):
    kind, instr, crit = wire["type"], wire.get("instructions") or "", wire.get("criteria")
    if kind == "choice":
        return Choice(instructions=instr, criteria={k: v or "" for k, v in crit.items()} if isinstance(crit, dict) else crit)
    if kind == "noul":
        return Noul(instructions=instr, criteria=crit)
    if kind == "score":
        return Score(instructions=instr, criteria=crit)
    raise ValueError(f"unknown question type {kind!r}")


if ROLE == "cross":
    # the cross model alone: no vector backbone in this package, so no TypeSafeClient (its engine loads one)
    from jul import cross
    from jul.engine import softmax
    reader = cross.load({"repo": str(CROSS_DIR), "subfolder": None}, "onnx")

    def answer(state: str, q) -> dict:
        kind, opts = type(q).__name__.lower(), options_of(q)
        logits, _ = reader.logits(state, kind, q.instructions, opts)
        return _format(kind, q, opts, softmax(logits)).as_dict()
else:
    from jul import TypeSafeClient
    client = TypeSafeClient(model=MODEL, backend="onnx")

    def answer(state: str, q) -> dict:
        return client.system_one(state, {"q": q}).answers["q"].as_dict()

# load the graphs at init, not on the first player's call
answer("warm-up", Noul(instructions="ready?") if ROLE == "cross" else Choice(criteria=["a", "b"]))
INIT_S = round(time.perf_counter() - T0, 2)


def handler(event, context=None):
    if event.get("warmup"):
        return {"warm": True, "role": ROLE, "init_s": INIT_S}
    t = time.perf_counter()
    state, answers = str(event["state"]), {}
    for name, wire in (event.get("questions") or {}).items():
        if ROLE not in KINDS.get(wire.get("type"), ()):
            raise ValueError(f"this function ({ROLE}) does not read {wire.get('type')!r} questions")
        answers[name] = answer(state, question(wire))
    return {"answers": answers, "ms": round((time.perf_counter() - t) * 1000, 1), "role": ROLE}
