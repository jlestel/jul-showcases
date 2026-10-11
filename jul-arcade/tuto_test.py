"""Plays the level-1 tutorial in a real browser as a new player would, screenshot at every step.

    python server.py &   then   QA_CHROME=<chrome> python tuto_test.py <out_dir>
Checks: the tutorial opens on first visit, "Suivant" stays locked until the asked input is filled, the
wave and end card advance it, it ends and does not reopen on reload. Prints the steps seen, JS errors.
"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(sys.argv[1] if len(sys.argv) > 1 else "tuto-shots"); out.mkdir(parents=True, exist_ok=True)
seen, errs = [], []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("QA_CHROME"),
                          args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 1600, "height": 900})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8600")
    pg.wait_for_selector("#coach", state="visible", timeout=60000)
    pg.evaluate("document.querySelector('#speed').value = '4'")

    def step():
        return pg.inner_text("#coach h4"), pg.inner_text("#coach .step")

    def shot(tag):
        t, n = step(); seen.append(f"{n} {t}"); time.sleep(0.4)
        pg.screenshot(path=str(out / f"{len(seen):02d}-{tag}.png"), timeout=90000)

    for tag in ("intro", "portes", "machine"):
        shot(tag); pg.click("#tNext")
    shot("description")                                    # step 4: locked until the description is written
    locked = pg.is_disabled("#tNext")
    fill_hidden = pg.evaluate("getComputedStyle(document.querySelector('#tFill')).visibility") == "hidden"
    pg.fill("#builder .node.choice > .sub > .row:nth-of-type(2) input.d", "paiement, facture, prélèvement, remboursement, prix")
    time.sleep(1.6)                                        # auto-advance after the todo is done
    shot("autres")
    time.sleep(15.5); fill_shown = pg.is_visible("#tFill")  # "remplis pour moi" appears after 15 s
    pg.click("#tFill")
    time.sleep(1.4)
    shot("lancer")
    pg.click("#go")
    pg.wait_for_function("document.querySelector('#coach h4').innerText.startsWith('Regarde')", timeout=120000)
    time.sleep(3); shot("vague")
    pg.wait_for_function("document.querySelector('#coach h4').innerText.startsWith('Ton')", timeout=600000)
    wire = pg.inner_text("#wire")[-400:]
    shot("resultat"); res = pg.evaluate("window.LAST && {c: LAST.correct, t: LAST.total, s: LAST.stars}")
    pg.click("#tNext"); shot("fin"); pg.click("#tNext")
    closed = not pg.is_visible("#coach")
    pg.reload(); time.sleep(6); reopened = pg.is_visible("#coach")
    b.close()
print(json.dumps({"steps": seen, "next_locked_until_filled": locked, "fill_hidden_then_shown": [fill_hidden, fill_shown], "wire": wire, "result": res, "closed": closed,
                  "reopens_on_reload": reopened, "js_errors": errs}, ensure_ascii=False, indent=1))
