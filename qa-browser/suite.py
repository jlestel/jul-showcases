"""suite — run many qa-browser tickets as a regression suite, filtered by tag.

    python qa-browser/suite.py qa-browser/tickets/*.md                     # everything
    python qa-browser/suite.py qa-browser/tickets/*.md --tag smoke         # only @smoke
    python qa-browser/suite.py qa-browser/tickets/*.md --tag checkout,auth --cdp http://localhost:9250
    python qa-browser/suite.py qa-browser/tickets/*.md --exclude auth      # skip the signed-in ones

Each ticket runs `run.py` unchanged and independently — a ticket that needs a full cart brings its
own via a `Setup :` fragment, so nothing depends on another ticket's leftovers or on the order. The
model loads once for the whole suite (so a 20-ticket run pays the ~10 s warmup a single time), and
the exit code is non-zero if any ticket fails, ready for CI. Still $0: no tokens are ever generated.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time
from argparse import Namespace
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import run as qa          # noqa: E402
from ticket import parse  # noqa: E402


def select(paths, want, drop):
    frags = HERE / "fragments"
    out = []
    for p in paths:
        t = parse(Path(p).read_text(encoding="utf-8"), fragments_dir=frags)
        tags = set(t.tags)
        if want and not (tags & want):
            continue
        if tags & drop:
            continue
        out.append((p, t))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tickets", nargs="+", help="ticket files or globs")
    ap.add_argument("--tag", help="run only tickets carrying any of these tags (comma-separated)")
    ap.add_argument("--exclude", help="skip tickets carrying any of these tags (comma-separated)")
    ap.add_argument("--cdp", help="drive an already open browser, e.g. http://localhost:9222")
    ap.add_argument("--chrome", help="Chromium executable to launch")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--replay", action="store_true", help="reuse the last trace for each ticket")
    args = ap.parse_args()

    paths = [p for pat in args.tickets for p in sorted(glob.glob(pat))]
    want = {t.strip() for t in args.tag.split(",")} if args.tag else None
    drop = {t.strip() for t in args.exclude.split(",")} if args.exclude else set()
    picked = select(paths, want, drop)
    if not picked:
        print("No ticket matched the tag filter.")
        sys.exit(1)

    results = []
    for i, (p, t) in enumerate(picked, 1):
        tagstr = f"  [{', '.join(t.tags)}]" if t.tags else ""
        print(f"\n━━━ [{i}/{len(picked)}] {t.title}{tagstr} ━━━")
        run_args = Namespace(replay=args.replay, cdp=args.cdp, chrome=args.chrome, headed=args.headed,
                             shot=None, trace=str(HERE / "runs" / (Path(p).stem + ".json")))
        t0 = time.perf_counter()
        try:
            code = qa.run(t, run_args)
        except Exception as e:                              # a crash is a fail, never sinks the suite
            print(f"✗ crashed: {e}")
            code = 1
        results.append((t.title, code == 0, time.perf_counter() - t0))

    ok = sum(1 for _, passed, _ in results if passed)
    print("\n" + "=" * 64)
    for title, passed, dt in results:
        print(f"  {'✓' if passed else '✗'} {title}   ({dt:.0f} s)")
    print(f"\n{ok}/{len(results)} green — 0 tokens generated, $0.00")
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
