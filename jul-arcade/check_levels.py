"""Level QA: play the reference machines of solutions.json against the real model.

A level ships only if the good machine reaches 2 stars or more and the lazy one does worse:
otherwise writing a good decision is not what wins, and the level is not a game.

    python check_levels.py                       # in-process JuL
    python check_levels.py --url http://127.0.0.1:8577   # any System One server
"""

import argparse
import json
from pathlib import Path

from engine import HttpBrain, LocalBrain, play

HERE = Path(__file__).parent

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="jul-decision-e5-small")
ap.add_argument("--backend", default=None)
ap.add_argument("--url", default=None)
ap.add_argument("-v", action="store_true", help="print every misrouted item")
a = ap.parse_args()

brain = HttpBrain(a.url) if a.url else LocalBrain(a.model, a.backend)
levels = {l["id"]: l for l in json.loads((HERE / "levels.json").read_text())["levels"]}
sols = json.loads((HERE / "solutions.json").read_text())
ok_all = True
for lid, level in levels.items():
    res = {}
    for kind in [k for k in ("lazy", "naive", "good") if k in sols[lid]]:
        r = play(brain, level, sols[lid][kind])
        res[kind] = r
        print(f"{lid:8s} {kind:4s} {r['correct']:2d}/{r['total']} ({r['accuracy']:.0%}) {'★' * r['stars']:3s} "
              f"score {r['score']:4d}  {r['calls']} calls, {r['ms_per_call']} ms/call")
        if a.v:
            for i in r["items"]:
                if not i["ok"]:
                    print(f"     ✗ {i['expected']:>11s} → {i['got']:11s} {i['text'][:70]}")
    passes = res["good"]["stars"] >= 2 and res["good"]["accuracy"] > res["lazy"]["accuracy"]
    ok_all &= passes
    print(f"{lid:8s} {'SHIP' if passes else 'REWORK'}\n")
print("all levels ship" if ok_all else "some levels need rework")
