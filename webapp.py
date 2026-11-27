"""Minimal web UI for the image scrub.

    pip install flask
    python webapp.py            # serves on http://localhost:7860

Single page: drag in one or more images (or a .zip), pick a level, download a
.zip of scrubbed results plus a JSON report. Runs fully locally.
"""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from dataclasses import asdict
from pathlib import Path

from flask import Flask, request, send_file

from image_scrub.pipeline import IMAGE_EXTS, process, summarize

app = Flask(__name__)

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>Image Scrub</title><style>
body{font-family:system-ui;background:#14151a;color:#e8e8e8;max-width:640px;
margin:4em auto;padding:0 1em}
h1{font-size:1.4em;letter-spacing:.05em}
.drop{border:2px dashed #555;border-radius:12px;padding:3em;text-align:center;
margin:1.5em 0}
select,button{background:#23252e;color:#e8e8e8;border:1px solid #555;
border-radius:8px;padding:.5em 1em;font-size:1em}
button{cursor:pointer;background:#3a5bd0;border-color:#3a5bd0}
small{color:#999}
pre{background:#1d1f26;padding:1em;border-radius:8px;overflow:auto}
</style></head><body>
<h1>IMAGE SCRUB</h1>
<form method=post action=/scrub enctype=multipart/form-data>
<div class=drop><input type=file name=files multiple
accept=".png,.jpg,.jpeg,.webp,.zip"><br>
<small>images or a .zip of a folder</small></div>
<label>Level
<select name=level>
<option value=0>0 — metadata strip only (lossless, pixel-identical)</option>
<option value=1>1 — clean re-encode (q97)</option>
<option value=2>2 — q90 + resample + faint noise</option>
<option value=3>3 — aggressive (micro-crop, jitter, q88)</option>
</select></label>
<button type=submit>Scrub</button>
</form>
{% if summary %}<h2>Results</h2><pre>{{summary}}</pre>{% endif %}
</body></html>"""

from jinja2 import Template  # bundled with Flask


@app.get("/")
def index():
    return Template(PAGE).render()


@app.post("/scrub")
def scrub():
    level = int(request.form.get("level", 0))
    uploads = request.files.getlist("files")
    if not uploads or not uploads[0].filename:
        return Template(PAGE).render(summary="No files uploaded.")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        src = td / "in"
        src.mkdir()
        for up in uploads:
            dest = src / Path(up.filename).name
            up.save(dest)
            if dest.suffix.lower() == ".zip":
                with zipfile.ZipFile(dest) as z:
                    z.extractall(src)
                dest.unlink()

        out_dir = td / "out"
        results = process(src, out_dir, level=level)
        summary = summarize(results)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for r in results:
                if r.output:
                    z.write(r.output, Path(r.output).name)
            z.writestr("report.json",
                       json.dumps([asdict(r) for r in results], indent=2))
        buf.seek(0)
        return send_file(buf, mimetype="application/zip",
                         as_attachment=True,
                         download_name=f"scrubbed-L{level}.zip")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860)
