"""Raw values of candidate Noul / Score formulations per expected portal, to size thresholds."""
import json, sys
from pathlib import Path
from engine import LocalBrain, to_wire

brain = LocalBrain("jul-decision-e5-small", "torch")
levels = {l["id"]: l for l in json.loads((Path(__file__).parent / "levels.json").read_text())["levels"]}
CANDS = {
  "tempete": [
    {"type": "noul", "instructions": "Le client est-il en colère ?"},
    {"type": "noul", "instructions": "Is the customer angry?"},
    {"type": "noul", "instructions": "Le client est-il furieux et insultant ?"},
    {"type": "score", "instructions": "À quel point le client est-il énervé ?", "levels": ["calme", "agacé", "furieux"]},
    {"type": "score", "instructions": "How angry is the customer?", "levels": ["calm", "annoyed", "furious"]},
  ],
  "avis": [
    {"type": "noul", "instructions": "Le client est-il satisfait ?"},
    {"type": "noul", "instructions": "Is this a positive review?"},
    {"type": "noul", "instructions": "L'avis est-il positif ?"},
    {"type": "score", "instructions": "À quel point le client est-il satisfait ?", "levels": ["très mécontent", "mécontent", "neutre", "content", "ravi"]},
    {"type": "score", "instructions": "How satisfied is the customer?", "levels": ["very unhappy", "unhappy", "neutral", "happy", "delighted"]},
    {"type": "score", "instructions": "Note de l'avis", "levels": ["négatif", "positif"]},
  ],
}
POS = {"tempete": "responsable", "avis": "fans"}
for lid, cands in CANDS.items():
    for c in cands:
        w = to_wire(c)
        pos, neg = [], []
        for it in levels[lid]["wave"]:
            a = brain.ask(it["text"], w)
            v = a["noul"] if w["type"] == "noul" else a["score"] / (len(w["criteria"]) - 1)
            (pos if it["portal"] == POS[lid] else neg).append(round(v, 2))
        auc = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))
        best = max(((sum(p >= t for p in pos) + sum(n < t for n in neg)) / (len(pos) + len(neg)), t)
                   for t in [x / 100 for x in range(1, 100)])
        print(f"{lid} {w['type']:5s} AUC {auc:.2f} best acc {best[0]:.0%} @ {best[1]:.2f} | {c['instructions']}")
        print(f"   pos {sorted(pos)}\n   neg {sorted(neg)}", flush=True)
