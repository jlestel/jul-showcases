"""Screenshot mid-wave (for the README): build the reference machine, launch, shoot during the animation."""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

level, out = sys.argv[1], sys.argv[2]
sol = json.loads((Path(__file__).parent / "solutions.json").read_text())[level]["good"]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("QA_CHROME"))
    pg = b.new_page(viewport={"width": 1400, "height": 820})
    pg.goto("http://127.0.0.1:8600"); pg.wait_for_function("typeof LEVELS !== 'undefined' && LEVELS.length > 0")
    pg.click(f"#levels button >> nth={pg.evaluate(f'LEVELS.findIndex(l => l.id === {json.dumps(level)})')}")
    pg.evaluate(f"MACHINE = {json.dumps(sol)}; render(); document.querySelector('#speed').value = '1'")
    pg.click("#go")
    pg.wait_for_function("document.querySelectorAll('#log div').length >= 4", timeout=120000)
    time.sleep(0.9)
    pg.screenshot(path=out)
    b.close()
