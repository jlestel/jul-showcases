#!/usr/bin/env bash
# Builds what the CDK stack deploys, under aws/build/:
#   game/       the game API (engine.py, levels.json, game_handler.py): stdlib + boto3 from the runtime
#   choice/     zip mode: jul[onnx] + the vector model (model/), ROLE=choice       (~200 MB, limit 250)
#   cross/      zip mode: jul[onnx] + the cross model (model-cross/), ROLE=cross   (~215 MB, limit 250)
#   container/  container mode: Dockerfile + both models; the image is built by `cdk deploy` (Docker needed)
#   web/        the front (S3 + CloudFront)
# Following jul's docs/aws-lambda.md: Linux wheels for the Lambda's CPU and Python 3.12, no Docker needed
# for the zips.
#
# Usage: aws/scripts/build.sh [arm64|x86_64]
#   JUL=<pip spec or checkout>   default "jul>=0.5.1"
#   MODEL_DIR=<local copy of usejul/jul-decision-e5-small-onnx>  default: downloaded with `hf`/`huggingface-cli`
set -euo pipefail
cd "$(dirname "$0")/.."           # aws/
ARCH=${1:-arm64}
JUL=${JUL:-jul>=0.5.1}
REPO=usejul/jul-decision-e5-small-onnx
OUT=build
case "$ARCH" in
  arm64) PLAT=aarch64; ;;
  x86_64) PLAT=x86_64 ;;
  *) echo "arch: arm64 or x86_64" >&2; exit 1 ;;
esac

# pip or uv, whichever is there: Linux wheels for $ARCH and CPython 3.12, whatever machine builds
wheels() {   # wheels <target> [--no-deps] <specs...>
  local target=$1; shift
  if command -v uv >/dev/null; then
    uv pip install -q --target "$target" --python-platform "$PLAT-manylinux_2_28" --python-version 3.12 \
      --only-binary=:all: "$@"
  else
    python3 -m pip install -q --target "$target" --platform "manylinux2014_$PLAT" --platform "manylinux_2_28_$PLAT" \
      --implementation cp --python-version 3.12 --only-binary=:all: "$@"
  fi
}
jul_pkg() {  # jul itself is pure Python: no platform flags
  if command -v uv >/dev/null; then uv pip install -q --target "$1" --no-deps "$JUL"
  else python3 -m pip install -q --target "$1" --no-deps "$JUL"; fi
}

if [ -z "${MODEL_DIR:-}" ]; then
  MODEL_DIR=$OUT/hf/jul-decision-e5-small-onnx
  if [ ! -f "$MODEL_DIR/model.onnx" ]; then
    if command -v hf >/dev/null; then hf download "$REPO" --local-dir "$MODEL_DIR"
    else huggingface-cli download "$REPO" --local-dir "$MODEL_DIR"; fi
  fi
fi
rm -rf "$OUT"/{game,choice,cross,container,web}

# --- the game API --------------------------------------------------------------------------------------
mkdir -p "$OUT/game"
cp ../engine.py ../levels.json lambda/game_handler.py "$OUT/game/"

# --- the model functions -------------------------------------------------------------------------------
deps() {   # deps <dir>: jul[onnx] runtime, trimmed as in docs/aws-lambda.md
  local d=$1
  wheels "$d" "onnxruntime>=1.18" "jinja2>=3.1" "numpy>=1.24"
  wheels "$d" --no-deps "tokenizers>=0.20"      # its Hub dependencies only download models
  jul_pkg "$d"
  rm -rf "$d"/onnxruntime/{transformers,quantization,tools} "$d"/numpy/_core/tests "$d"/numpy/tests "$d"/bin "$d"/jul_cli
  find "$d" -name __pycache__ -type d -prune -exec rm -rf {} +
}
vector_model() { mkdir -p "$1"; for f in "$MODEL_DIR"/*; do [ -f "$f" ] && [ "$(basename "$f")" != README.md ] && cp "$f" "$1/"; done; }
cross_model() { mkdir -p "$1"; cp "$MODEL_DIR"/cross/* "$1/"; }
handler() { cp lambda/model_handler.py "$1/"; cp -r preset "$1/preset"; }

deps "$OUT/choice"; handler "$OUT/choice"; vector_model "$OUT/choice/model"
mkdir -p "$OUT/cross"; cp -r "$OUT/choice/." "$OUT/cross/"; rm -rf "$OUT/cross/model"; cross_model "$OUT/cross/model-cross"

# --- the container (both models in one image) ----------------------------------------------------------
mkdir -p "$OUT/container"
cp container/Dockerfile "$OUT/container/"
handler "$OUT/container"; vector_model "$OUT/container/model"; cross_model "$OUT/container/model-cross"
echo "$JUL" > "$OUT/container/jul-spec.txt"
[ -d "$JUL" ] && { rm -rf "$OUT/container/jul-src"; cp -r "$JUL" "$OUT/container/jul-src"; rm -rf "$OUT/container/jul-src"/{.git,.venv*,site,tests}; echo ./jul-src > "$OUT/container/jul-spec.txt"; }

# --- the front -----------------------------------------------------------------------------------------
cp -r ../web "$OUT/web"

du -sm "$OUT"/{game,choice,cross,container,web}
for d in choice cross; do
  mb=$(du -sm "$OUT/$d" | cut -f1)
  [ "$mb" -lt 250 ] || { echo "$d: $mb MB, over Lambda's 250 MB unzipped" >&2; exit 1; }
done
