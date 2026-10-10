"""Screenshots of the 3D page: idle, mid-wave, end card. Prints JS errors and the result.

    python shot3d.py <level> <prefix>
"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

level, prefix = sys.argv[1], sys.argv[2]
sol = json.loads((Path(__file__).parent / "solutions.json").read_text())[level]["good"]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("QA_CHROME"),
                          args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 1600, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
    pg.goto("http://127.0.0.1:8600")
    pg.wait_for_function("typeof LEVELS !== 'undefined' && LEVELS.length > 0 && window.STAGE", timeout=60000)
    pg.click(f"#levels button >> nth={pg.evaluate(f'LEVELS.findIndex(l => l.id === {json.dumps(level)})')}")
    pg.evaluate(f"MACHINE = {json.dumps(sol)}; render(); document.querySelector('#speed').value = '1'")
    time.sleep(1.5); pg.screenshot(path=f"{prefix}-idle.png")
    t = time.time(); pg.click("#go")
    pg.wait_for_function("document.querySelectorAll('#log div').length >= 2", timeout=180000)
    time.sleep(1.2); pg.screenshot(path=f"{prefix}-mid.png")
    pg.evaluate("document.querySelector('#speed').value = '4'")
    pg.wait_for_function("document.querySelector('#end').classList.contains('on')", timeout=400000)
    time.sleep(1.5); pg.screenshot(path=f"{prefix}-end.png")
    print(json.dumps({"result": pg.evaluate("LAST && {c: LAST.correct, t: LAST.total, s: LAST.stars}"),
                      "errors": errs, "s": round(time.time() - t, 1)}))
    b.close()
