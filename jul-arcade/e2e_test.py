"""End-to-end check in a real browser: open the game, build the reference machine of a level
through the UI, launch the wave, wait for the animation to finish, read the HUD.

    python server.py &          # then
    python e2e_test.py [--level guichet] [--shot out.png]
"""
import argparse, json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8600")
ap.add_argument("--level", default="guichet")
ap.add_argument("--shot", default="e2e.png")
ap.add_argument("--chrome", default=os.environ.get("QA_CHROME"))
a = ap.parse_args()
sol = json.loads((Path(__file__).parent / "solutions.json").read_text())[a.level]["good"]

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(a.url); pg.wait_for_function("typeof LEVELS !== 'undefined' && LEVELS.length > 0")
    idx = pg.evaluate(f"LEVELS.findIndex(l => l.id === {json.dumps(a.level)})")
    pg.click(f"#levels button >> nth={idx}")
    # build the machine through the UI for the root (type + texts), then the rest by state
    pg.select_option("#builder .node .head select", sol["type"])
    pg.fill("#builder .node > input", sol["instructions"])
    if sol["type"] == "choice":
        for i, o in enumerate(sol["options"]):
            row = pg.locator("#builder .node .sub .row").nth(i)
            row.locator("input.k").fill(o["key"]); row.locator("input.d").fill(o["description"])
            row.locator("select.dest").select_option(o["to"] if isinstance(o["to"], str) else "+" + o["to"]["type"])
    pg.evaluate(f"MACHINE = {json.dumps(sol)}; render();")   # nested branches + thresholds
    t = time.time()
    pg.click("#go")
    pg.wait_for_function("document.querySelector('#h-score').textContent.includes('★') || "
                         "document.querySelector('#err').textContent", timeout=240000)
    time.sleep(1.0)
    hud = pg.evaluate("[...document.querySelectorAll('#hud .chip')].map(e => e.textContent)")
    err = pg.text_content("#err")
    res = pg.evaluate("window.LAST && {correct: LAST.correct, total: LAST.total, stars: LAST.stars, ms: LAST.ms_per_call}")
    log_lines = pg.evaluate("[...document.querySelectorAll('#log div')].length")
    pg.screenshot(path=a.shot)
    print(json.dumps({"level": a.level, "hud": hud, "result": res, "log_lines": log_lines, "err": err,
                      "js_errors": errors, "seconds": round(time.time() - t, 1)}, ensure_ascii=False))
    b.close()
