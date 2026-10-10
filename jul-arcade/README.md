# JuL Arcade · L'aiguilleur

A puzzle game where the player **builds the decision**, not the input. Messages roll in on a
conveyor; the player assembles a small machine of typed decisions (`Choice`, `Noul`, `Score`) and
launches the wave. Every block is a real `system_one` call to JuL: the robot hesitates when the
model is unsure, and the result is scored. The game teaches the API without a tutorial: which
question type, how to word the criteria, where to put the threshold, how to chain decisions.

```console
$ python server.py --backend torch
brain ready: jul-decision-e5-small (local) (19.5s) -> http://127.0.0.1:8600
[play] guichet: 14/18 ★★ 18 calls 43.3 ms/call
[play] tempete: 13/17 ★★ 30 calls 27.8 ms/call
[play] avis: 13/14 ★★★ 14 calls 64.5 ms/call
```

## Game design (v1)

- **Loop**: read the brief and 2-3 examples → build the machine → ▶ launch the wave → watch the
  robot route each message (a decision bubble per call, sweat + "?" under 0.35 confidence) → stars.
- **Blocks** (one per question type, the same JSON as the Jev/JuL HTTP API):
  - `Choice`: N options, each a name, a criterion, and an exit (portal or another block);
  - `Noul`: a yes/no question, a threshold slider, two exits;
  - `Score`: ordered levels, a threshold along them, two exits (above / below).
- **Chaining**: an exit can be another block (up to 4 deep), so level 2 is "angry? → manager,
  else → which team?": the real pipeline pattern.
- **Score**: 1000 × accuracy on the wave, minus 5 per word above 15, minus 50 per extra block.
  Stars: ≥ 90 % ★★★, ≥ 75 % ★★, ≥ 50 % ★. The wave's answers never reach the browser before play.
- **HUD**: correct / total, ms per decision, number of calls, and "0 token · 0 $".
- **Levels** (`levels.json`, data only, nothing level-specific in the code):
  1. *Le guichet*: one Choice, three teams. Lesson: options must describe themselves.
  2. *La tempête*: Noul (or Score) then Choice. Lesson: chaining, and the threshold matters.
  3. *Le mur des avis*: Score with a threshold. Lesson: a Score's scale is not centred on 0.5.

## Level QA: a level ships only if it is a game

`check_levels.py` plays the reference machines of `solutions.json` against the real model. A level
ships when the good machine reaches ★★ and beats the lazy one (option names only, default
threshold). With `jul-decision-e5-small`, torch CPU on the pod:

| level | lazy | naive | good |
| --- | ---: | ---: | ---: |
| guichet | 11/18 ★ | – | 14/18 ★★ |
| tempete | 10/17 ★ | 12/17 ★ (Noul at 0.5) | 13/17 ★★ (Noul at 0.95) |
| avis | 9/14 ★ | 7/14 ★ (Score at 0.5) | 13/14 ★★★ (Score at 0.69) |

Found on the way: the Noul "is the customer angry?" scores polite technical complaints 0.85-0.93
(threshold 0.95 needed), and the satisfaction Score puts every review between 0.52 and 0.79: the
threshold is the puzzle of level 3. A 3-level Score "how annoyed?" separates level 2 perfectly
(AUC 1.00 at 0.35, `probe_values.py`) but routes some calm messages wrong in the chained run.

## Run

```bash
pip install "jul[torch]"     # or [mlx] on a Mac, [onnx] for the Lambda build
jul models add jul-decision-e5-small --repo usejul/jul-decision-e5-small --backend torch
python server.py --backend torch           # http://127.0.0.1:8600
python check_levels.py --backend torch -v  # level QA
python e2e_test.py --level guichet         # browser end-to-end (server running)
python server.py --url http://127.0.0.1:8577   # or any System One server: jul serve, a Lambda, Jev
```

Standard library server, one HTML file (Canvas 2D, no build step). The brain is in-process JuL or
any server speaking the System One protocol (`HttpBrain`).

## Not done yet

See `PLAN.md`.
