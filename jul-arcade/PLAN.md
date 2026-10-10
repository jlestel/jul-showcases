# JuL Arcade: implementation plan

## v1 (this branch): playable end to end, local
- [x] Level format (`levels.json`), machine format = the System One question JSON + exits.
- [x] Engine: validation, routing through chained blocks, scoring (`engine.py`).
- [x] Brains: in-process JuL, or any System One URL (`jul serve`, Lambda, Jev).
- [x] Front: one HTML file, block builder, Canvas stage (conveyor, kawaii robot, portals), HUD, log.
- [x] 3 levels (Choice / Noul+Choice / Score), each checked by `check_levels.py`.
- [x] Browser e2e (`e2e_test.py`): 3/3 levels played through the UI, no JS error.

## v2: make it fun (game feel)
- Drag and drop blocks on a 2D board instead of the form (rails between blocks, à la Mini Metro).
- Robot animation driven by the probabilities (hesitates between the two top portals, sprint at > 0.9).
- Sound, combo counter, end-of-level card with the API call to copy ("this is your production code").
- Hidden **test wave** besides the shown one, so the player cannot overfit the examples.
- 5-8 more levels, each with one lesson: option overlap, "none of the above", Score levels,
  chaining depth vs cost, long messages, two languages. Every level must pass `check_levels.py`.
- Share: export a 10 s GIF/MP4 of the wave + score (MediaRecorder on the canvas).

## v3: hosted
- Brain = `jul-decision-e5-small` ONNX in AWS Lambda (function URL, `jul serve` protocol); the game
  is a static page on S3/CloudFront. Measure cold start and per-call latency of the cross model in
  Lambda (not measured yet: only the vectors are, 17 ms for 2 questions).
- Cache: the same (text, question) pair is replayed for free; the wave replays instantly.
- Leaderboard per level (best score, fewest words), machines stored as JSON. Rate limit per IP.
- Option vectors change with every edit: the first wave after an edit is the slow one (first
  call ~1 s on the pod CPU, then 20-65 ms per decision). Warm the options on edit, not on launch.

## v4: autotune as a power-up
- Spend a budget of labelled examples; autotune runs for real. Measured on the pod CPU: 45-65 s for
  80-120 examples, too slow inside a wave: an end-of-level "training" screen, or a Lambda with more CPU.

## Open questions for the team
- Theme: support tickets (now), parcels, airport? One theme or one per world?
- Public data: nothing typed by the player leaves the machine except the machine JSON.
