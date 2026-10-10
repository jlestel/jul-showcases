"""The game API behind API Gateway (REST, Lambda proxy): levels, play, warmup. No model here.

    GET  /api/levels  -> the levels, without the wave's answers
    POST /api/play    -> {"level": id, "machine": {...}}: runs the machine over the wave (engine.play)
    GET  /api/warmup  -> pings the model functions so the first wave does not pay their cold start

Each decision of the machine is one invocation of a model function, chosen by question type:
CHOICE_FN for Choice, CROSS_FN for Noul and Score (zip mode: two functions), or the same function for
both (container mode: one image with the two models).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import boto3
from botocore.config import Config

from engine import MachineError, play

HERE = Path(__file__).resolve().parent
LEVELS = json.loads((HERE / "levels.json").read_text())["levels"]
BY_ID = {l["id"]: l for l in LEVELS}
CHOICE_FN, CROSS_FN = os.environ["CHOICE_FN"], os.environ["CROSS_FN"]
MODEL_FNS = sorted({CHOICE_FN, CROSS_FN})
lam = boto3.client("lambda", config=Config(read_timeout=60, retries={"max_attempts": 2}))


def invoke(fn: str, payload: dict) -> dict:
    out = lam.invoke(FunctionName=fn, Payload=json.dumps(payload).encode())
    body = json.loads(out["Payload"].read())
    if out.get("FunctionError"):
        raise RuntimeError(f"{fn}: {body.get('errorMessage', body)}")
    return body


class LambdaBrain:
    name = "jul-decision-e5-small (AWS Lambda)"

    def ask(self, text: str, wire: dict) -> dict:
        fn = CHOICE_FN if wire["type"] == "choice" else CROSS_FN
        return invoke(fn, {"state": text, "questions": {"q": wire}})["answers"]["q"]


BRAIN = LambdaBrain()


def public_level(l: dict) -> dict:
    return {k: l[k] for k in ("id", "title", "brief", "tools", "portals", "starter", "examples")} | {
        "wave_size": len(l["wave"]), "hint": l.get("hint", "")}


def reply(code: int, body: dict) -> dict:
    return {"statusCode": code, "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
            "body": json.dumps(body, ensure_ascii=False)}


def warmup() -> dict:
    # Fire-and-forget: an async (InvocationType="Event") invoke returns at once, so a slow cold start
    # (the container image loads both models in ~28 s) is not held behind API Gateway's 29 s synchronous
    # limit, which used to time the first warmup out. We no longer wait for the models' init_s.
    for fn in MODEL_FNS:
        lam.invoke(FunctionName=fn, InvocationType="Event", Payload=json.dumps({"warmup": True}).encode())
    return {"warming": True, "functions": MODEL_FNS}


def handler(event, context=None):
    path, method = event.get("resource") or event.get("path", ""), event.get("httpMethod", "GET")
    try:
        if path.endswith("/levels") and method == "GET":
            return reply(200, {"levels": [public_level(l) for l in LEVELS], "brain": BRAIN.name})
        if path.endswith("/warmup"):
            return reply(200, warmup())
        if path.endswith("/play") and method == "POST":
            body = json.loads(event.get("body") or "{}")
            t = time.time()
            res = play(BRAIN, BY_ID[body["level"]], body["machine"])
            res["wall_s"] = round(time.time() - t, 2)
            return reply(200, res)
        return reply(404, {"error": "not found"})
    except MachineError as e:
        return reply(400, {"error": str(e)})
    except KeyError as e:
        return reply(400, {"error": f"champ manquant : {e}"})
    except Exception as e:  # noqa: BLE001
        return reply(500, {"error": f"{type(e).__name__}: {e}"})
