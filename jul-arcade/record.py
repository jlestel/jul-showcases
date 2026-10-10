"""Record a wave of the 3D page to a video (Playwright screencast, then ffmpeg to mp4).

    python record.py <level> <out.mp4> [speed]
"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

level, out = sys.argv[1], sys.argv[2]
speed = sys.argv[3] if len(sys.argv) > 3 else "2"
sol = json.loads((Path(__file__).parent / "solutions.json").read_text())[level]["good"]
tmp = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("QA_CHROME"),
                          args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    ctx = b.new_context(viewport={"width": 1600, "height": 900}, record_video_dir=tmp, record_video_size={"width": 1600, "height": 900})
    pg = ctx.new_page()
    pg.goto("http://127.0.0.1:8600")
    pg.wait_for_function("typeof LEVELS !== 'undefined' && LEVELS.length > 0 && window.STAGE", timeout=60000)
    pg.click(f"#levels button >> nth={pg.evaluate(f'LEVELS.findIndex(l => l.id === {json.dumps(level)})')}")
    pg.evaluate(f"MACHINE = {json.dumps(sol)}; render(); document.querySelector('#speed').value = '{speed}'")
    time.sleep(2)
    pg.click("#go")
    pg.wait_for_function("document.querySelector('#end').classList.contains('on')", timeout=600000)
    time.sleep(3)
    ctx.close(); b.close()
src = next(Path(tmp).glob("*.webm"))
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale=1280:-2", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-crf", "26", "-movflags", "+faststart", out], check=True)
shutil.rmtree(tmp)
print(out)
