"""Polite downloader for the M3 audio scouting (docs/M3_AUDIO.md).

Downloads each listed file into ThirdParty_staging/audio/<source>/<slug>/, at most one request per
1.2 s, with a generic user agent and no personal data, and appends sha256 + source page to
ThirdParty_staging/audio/manifest.json. Downloaded files are untrusted data: this script never
executes or parses them, and archives are unpacked by a separate step.

Usage: python -I tools/assets/audio_fetch.py JOBS.json
JOBS.json: [{"source": "oga", "slug": "...", "page": "https://...", "url": "https://..."}]
"""
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STAGING = os.path.join(ROOT, "ThirdParty_staging", "audio")
MANIFEST = os.path.join(STAGING, "manifest.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) asset-scout/1.0"
MIN_GAP = 1.2
MAX_BYTES = 40 * 1024 * 1024


def load_manifest():
    try:
        with open(MANIFEST, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def main(jobs_path):
    with open(jobs_path, "r", encoding="utf-8") as f:
        jobs = json.load(f)
    manifest = load_manifest()
    known = {(m["url"]) for m in manifest}
    last = 0.0
    for job in jobs:
        if job["url"] in known:
            print("skip (already in manifest)", job["url"])
            continue
        folder = os.path.join(STAGING, job["source"], job["slug"])
        os.makedirs(folder, exist_ok=True)
        name = urllib.parse.unquote(job["url"].rsplit("/", 1)[-1])
        name = "".join(c if c.isalnum() or c in "._- []()" else "_" for c in name)
        out = os.path.join(folder, name)
        gap = time.time() - last
        if gap < MIN_GAP:
            time.sleep(MIN_GAP - gap)
        last = time.time()
        req = urllib.request.Request(job["url"], headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read(MAX_BYTES + 1)
                ctype = r.headers.get("Content-Type")
        except Exception as e:  # noqa: BLE001 - report and continue with the next file
            print("FAIL", job["url"], e)
            continue
        if len(data) > MAX_BYTES:
            print("TOO BIG, dropped", job["url"])
            continue
        with open(out, "wb") as f:
            f.write(data)
        entry = {
            "source": job["source"],
            "slug": job["slug"],
            "page": job["page"],
            "url": job["url"],
            "file": os.path.relpath(out, STAGING).replace("\\", "/"),
            "bytes": len(data),
            "content_type": ctype,
            "sha256": hashlib.sha256(data).hexdigest(),
            "downloaded": time.strftime("%Y-%m-%d"),
        }
        manifest.append(entry)
        with open(MANIFEST, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1)
        print("ok", entry["file"], entry["bytes"])


if __name__ == "__main__":
    main(sys.argv[1])
