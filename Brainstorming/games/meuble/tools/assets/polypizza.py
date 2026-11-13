"""Polite, scriptable access to poly.pizza (stdlib only).

Every HTTP request waits at least 1.1 s after the previous one. No login, no
API key, no personal data: only a generic User-Agent is sent. Pages are
parsed through the JSON state the site embeds (window.__SERVER_APP_STATE__);
nothing from the network is executed.

    python -I polypizza.py bundle <bundle-url-or-path> --out bundle.json
    python -I polypizza.py search <term> [--pages N] --out search.json
    python -I polypizza.py model <id> [<id> ...] --out models.json
    python -I polypizza.py download <id> --dest <dir> [--name file.glb] [--facts models.json]

"model" records the facts read on each model page: title, creator, licence,
poly.pizza triangle count, upload type, "Animated" flag, category, tags, and
the direct GLB URL found in the page HTML (cross-checked with ResourceID).
"download" saves the GLB found on the model page and prints its sha256.
"""

import hashlib
import html as htmllib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://poly.pizza"
USER_AGENT = "Mozilla/5.0 (compatible; asset-scout/1.0)"
MIN_INTERVAL = 1.1
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_GLB_BYTES = 60 * 1024 * 1024
STATE_RE = re.compile(r"window\.__SERVER_APP_STATE__\s*=\s*(\{.*?\})</script>", re.S)
GLB_RE = re.compile(r"https://static\.poly\.pizza/([0-9a-f-]{36})\.glb")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,16}$")
CC_LINK_RE = re.compile(r'href="(https?://creativecommons\.org/[^"]+)"')
LABEL_RE = re.compile(r"(?i)public domain|attribution|\bCC0\b|CC-BY")

_last_request = [0.0]


def fetch(url, limit=MAX_PAGE_BYTES):
    wait = MIN_INTERVAL - (time.monotonic() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read(limit + 1)
    finally:
        _last_request[0] = time.monotonic()
    if len(data) > limit:
        raise RuntimeError(f"response larger than {limit} bytes: {url}")
    return data


def page_state(html):
    m = STATE_RE.search(html)
    if not m:
        raise RuntimeError("no __SERVER_APP_STATE__ in page")
    return json.loads(m.group(1))["initialData"]


def card(item):
    return {
        "id": item.get("publicID"),
        "title": (item.get("title") or "").strip(),
        "creator": (item.get("creator") or {}).get("username"),
        "licence": item.get("licence"),
        "uuid": (item.get("previewUrl") or "").rsplit("/", 1)[-1].split(".")[0],
        "page": BASE + "/m/" + str(item.get("publicID")),
    }


def cmd_bundle(target):
    path = target if target.startswith("/bundle/") else "/bundle/" + target.rsplit("/bundle/", 1)[-1]
    html = fetch(BASE + urllib.parse.quote(path, safe="/-()!")).decode("utf-8", "replace")
    lst = page_state(html)["list"]
    return {
        "bundle": lst.get("Name"),
        "owner": (lst.get("Owner") or {}).get("Username"),
        "url": BASE + path,
        "models": [card(m) for m in lst.get("Models", [])],
    }


def cmd_search(term, pages):
    q = urllib.parse.quote(term)
    html = fetch(f"{BASE}/search/{q}").decode("utf-8", "replace")
    state = page_state(html)
    results = [card(m) for m in state.get("result", [])]
    total = state.get("resultCount")
    for page in range(1, pages):
        if len(results) >= (total or 0):
            break
        data = json.loads(fetch(f"{BASE}/api/search/{q}?Page={page}").decode("utf-8", "replace"))
        batch = data.get("results", [])
        if not batch:
            break
        results.extend(card(m) for m in batch)
    return {"term": term, "resultCount": total, "results": results}


def visible_licence(html):
    """Licence label and link as rendered in the page body (outside the JSON state)."""
    body = html.split("window.__SERVER_APP_STATE__")[0]
    link = CC_LINK_RE.search(body)
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", body, flags=re.S)
    lines = [ln.strip() for ln in htmllib.unescape(re.sub(r"<[^>]+>", "\n", text)).split("\n") if ln.strip()]
    label = next((ln for ln in lines if LABEL_RE.search(ln)), None)
    return label, link.group(1) if link else None


def cmd_model(model_id):
    if not ID_RE.match(model_id):
        raise ValueError(f"bad model id {model_id!r}")
    url = f"{BASE}/m/{model_id}"
    html = fetch(url).decode("utf-8", "replace")
    m = page_state(html)["model"]
    glbs = sorted(set(GLB_RE.findall(html)))
    resource = m.get("ResourceID")
    label, link = visible_licence(html)
    return {
        "id": model_id,
        "page": url,
        "title": (m.get("Title") or "").strip(),
        "creator": (m.get("Creator") or {}).get("Username"),
        "licence": m.get("Licence"),
        "licence_label": label,
        "licence_link": link,
        "tris_site": m.get("Tris"),
        "type": m.get("Type"),
        "animated_flag": m.get("Animated"),
        "category": m.get("Category"),
        "tags": m.get("Tags"),
        "upload_date": m.get("UploadDate"),
        "resource_id": resource,
        "glb_url": f"https://static.poly.pizza/{resource}.glb" if resource in glbs else None,
        "glb_urls_in_page": glbs,
    }


def cmd_download(model_id, dest, name, facts_file):
    facts = None
    if facts_file and Path(facts_file).exists():
        for f in json.loads(Path(facts_file).read_text(encoding="utf-8")):
            if f.get("id") == model_id:
                facts = f
    if facts is None:
        facts = cmd_model(model_id)
    if not facts.get("glb_url"):
        raise RuntimeError(f"no GLB URL found on page for {model_id}")
    data = fetch(facts["glb_url"], limit=MAX_GLB_BYTES)
    if data[:4] != b"glTF":
        raise RuntimeError("downloaded file is not a GLB")
    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / (name or f"{model_id}.glb")
    target.write_bytes(data)
    return {"id": model_id, "file": str(target), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "glb_url": facts["glb_url"]}


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    opts = {}
    args = []
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            opts[rest[i][2:]] = rest[i + 1]
            i += 2
        else:
            args.append(rest[i])
            i += 1
    if cmd == "bundle":
        result = cmd_bundle(args[0])
    elif cmd == "search":
        result = [cmd_search(t, int(opts.get("pages", "1"))) for t in args]
    elif cmd == "model":
        result = []
        for a in args:
            try:
                result.append(cmd_model(a))
            except Exception as exc:  # keep going on a single bad page
                result.append({"id": a, "error": repr(exc)})
            print(json.dumps(result[-1], ensure_ascii=False)[:300])
    elif cmd == "download":
        result = cmd_download(args[0], opts["dest"], opts.get("name"), opts.get("facts"))
        print(json.dumps(result))
    else:
        print(__doc__)
        return 2
    if "out" in opts:
        Path(opts["out"]).write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
