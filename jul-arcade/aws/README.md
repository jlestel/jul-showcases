# JuL Arcade on AWS (CDK, TypeScript)

```
CloudFront ─┬─ /*      → S3 (the game page, private bucket + origin access control)
            └─ /api/*  → API Gateway REST (stage "api") → Game Lambda (engine.py + levels.json, no model)
                                                            └─ invokes the model Lambda(s), one call per block
```

The player writes the questions, so there is no `jul pack` bundle: the model functions answer System
One questions sent in the event (`lambda/model_handler.py`), with `jul-decision-e5-small` (onnx) inside
the function. Each block of the player's machine is one invocation, routed by type:

| `-c packaging=` | Model functions | Why |
| --- | --- | --- |
| `zip` (default) | `ChoiceModel` (vector model, Choice) + `CrossModel` (cross model, Noul/Score), 214 MB each | jul's `docs/aws-lambda.md`: one model per zip, both do not fit 250 MB |
| `container` | `Model`, one arm64 image with both models | to compare: cold start of an image not measured anywhere yet |

The two modes are two stacks (`JulArcade`, `JulArcadeContainer`) and can live side by side.

**Warmup.** The page calls `GET /api/warmup` on load, while the player reads the brief: the game Lambda
pings each model function (`{"warmup": true}`), which answers with its init time. It warms one
instance of each: concurrent players beyond that still meet a cold start (provisioned concurrency if
that matters).

**Auth.** None yet: the three methods are open, throttled at 20 req/s (burst 40). An authorizer
(Cognito + social login) goes on the API's root later.

## Deploy (from a Mac)

```bash
cd jul-arcade/aws
scripts/build.sh arm64          # Linux arm64 wheels, no Docker; downloads the model from the Hub
cd infra && npm install
npx cdk bootstrap               # once per account/region
npx cdk deploy                  # zip mode
npx cdk deploy -c packaging=container   # container mode: Docker must be running
```

`JUL=<pip spec or local checkout>` picks the jul installed in the packages (default `jul>=0.5.1`);
`MODEL_DIR=<local copy of usejul/jul-decision-e5-small-onnx>` skips the download.
Output `Url` is the game.

## What was checked (on an x86 pod, nothing deployed)

- `build.sh arm64`: choice 214 MB, cross 214 MB (under 250), container context 198 MB.
- The handlers, run in-process with onnxruntime on the built model directories, give the same scores
  as the local torch game on the three levels (14/18 ★★, 13/17 ★★, 13/14 ★★★). Warm, on the pod's
  CPU: Choice 35-45 ms (≈120 ms the first time an option set is seen), Noul 13-18 ms, Score 65-95 ms
  (one cross pass per level). Init 1.2-1.4 s per function, 2.0 s with both models.
- The game handler, with the Lambda client faked by the model handler: warmup, levels (no answers
  leaked), a full wave routed to the right function (Choice → choice, Noul/Score → cross), a broken
  machine → 400.
- `tsc --noEmit` and `cdk synth` pass for both modes.

## To measure after the first deploy

- Cold start of each model function, zip vs container (the warmup reply carries `init_s`).
- Latency per decision in Lambda (arm64, 1,769 MB), the cross model has never been timed there.
- Wall time of a wave behind API Gateway (29 s limit: a wave is 15-35 sequential invocations).
- Cost per wave.
