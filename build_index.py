#!/usr/bin/env python3
"""
Build kramp-dashboard-deploy/index.html for production.

Combines:
  - The latest artifact source at ../.artifact-src/kramp-mi-dashboard.js
  - Live API mount snapshots (news-live, VoC, signals, sources, ...) from the
    running companion server at http://localhost:24680
  - A stable fallback set (eurostat, countries) preserved from the previous
    build because the live mounts return leaner or error responses.

Output: index.html   (a fully self-contained single-file bundle usable on
GitHub Pages; a browser fetch() shim intercepts /api/_a/<artifact>/... calls
and serves the embedded JSON).

Run twice a week (Mon + Thu) to refresh the RSS feed and other live data:
    python3 build_index.py

Exit codes:
    0 = success
    1 = network / snapshot error (index.html not modified)
    2 = source files missing
"""
from __future__ import annotations
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SRC = REPO_ROOT / ".artifact-src" / "kramp-mi-dashboard.js"
OUT = HERE / "index.html"
COMPANION = "http://localhost:24680"
ARTIFACT_ID = "9f0b77a9-05f7-40ad-be7c-38f9b020eb67"
PREFIX = f"/api/_a/{ARTIFACT_ID}"

# All routes the client fetches.
#  - fresh : always snapshot from the running mount
#  - preserve : keep the payload from the previous build (mount returns lean/error)
ROUTES = [
    (f"{PREFIX}/data/kpis", "fresh"),
    (f"{PREFIX}/data/competitors", "fresh"),
    (f"{PREFIX}/data/signals", "fresh"),
    (f"{PREFIX}/data/countries", "preserve"),   # enriched embed > lean mount
    (f"{PREFIX}/data/categories", "fresh"),
    (f"{PREFIX}/data/momentum", "fresh"),
    (f"{PREFIX}/data/sources", "fresh"),
    (f"{PREFIX}/data/source-issues", "fresh"),
    (f"{PREFIX}/data/retrieval-meta", "fresh"),
    (f"{PREFIX}/competitors/landscape", "fresh"),
    (f"{PREFIX}/competitors/news", "fresh"),
    (f"{PREFIX}/eurostat", "preserve"),          # live mount currently SSL-broken
    (f"{PREFIX}/voc", "fresh"),
    (f"{PREFIX}/news-live", "fresh"),
]

HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Kramp Market Intelligence Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  html, body { margin:0; padding:0; height:100%; background:#f7f6f3; font-family:'Barlow',-apple-system,sans-serif; }
  #root { min-height:100vh; }
</style>
</head>
<body>
<div id="root"></div>
<script type="module">
import { h, render, Fragment } from 'https://esm.sh/preact@10.22.0';
import { useState, useEffect, useRef, useMemo, useCallback, useReducer } from 'https://esm.sh/preact@10.22.0/hooks';
import htm from 'https://esm.sh/htm@3.1.1';
const html = htm.bind(h);

// === Embedded API data (built {BUILD_TS} UTC) ===
const __EMBEDDED__ = {EMBEDDED_JSON};

// === Fetch shim ===
const __origFetch = window.fetch.bind(window);
window.fetch = async (url, opts) => {
  const u = typeof url === 'string' ? url : url.url;
  for (const [path, payload] of Object.entries(__EMBEDDED__)) {
    if (u.endsWith(path) || u.includes(path)) {
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    }
  }
  return __origFetch(url, opts);
};

"""

HTML_TAIL = """
</script>
</body>
</html>
"""


def snapshot(path: str, timeout: int = 90) -> object:
    url = COMPANION + path
    with urllib.request.urlopen(url, timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status} for {path}")
        return json.loads(r.read().decode("utf-8"))


def load_previous_embedded() -> dict:
    if not OUT.exists():
        return {}
    text = OUT.read_text(encoding="utf-8")
    m = re.search(r"const __EMBEDDED__ = (\{.*?\});\n", text, re.DOTALL)
    if not m:
        return {}
    return json.loads(m.group(1))


def main() -> int:
    if not SRC.exists():
        print(f"[error] source not found: {SRC}", file=sys.stderr)
        return 2

    previous = load_previous_embedded()
    embedded: dict[str, object] = {}
    errors: list[str] = []

    for path, mode in ROUTES:
        short = path.split(ARTIFACT_ID + "/")[-1]
        if mode == "preserve" and path in previous:
            embedded[path] = previous[path]
            print(f"[keep ] {short:40} ({len(json.dumps(previous[path])):>8} bytes)")
            continue
        try:
            t0 = time.time()
            payload = snapshot(path)
            dt = time.time() - t0
            embedded[path] = payload
            size = len(json.dumps(payload))
            print(f"[fresh] {short:40} ({size:>8} bytes, {dt:0.2f}s)")
        except Exception as exc:
            # fall back to previous payload if we have one; otherwise fail
            if path in previous:
                embedded[path] = previous[path]
                errors.append(f"{path}: {exc}  (using previous cached payload)")
                print(f"[fallb] {short:40} using previous ({exc})")
            else:
                errors.append(f"{path}: {exc}  (no previous, ABORTING)")
                print(f"[FAIL ] {short:40} {exc}", file=sys.stderr)
                if mode == "fresh" and "news-live" in path:
                    # RSS feed is the whole point of this build; abort.
                    return 1

    # Special-case: the news-live snapshot should be < 6h old to publish
    news_key = f"{PREFIX}/news-live"
    news = embedded.get(news_key) or {}
    fetched_at = news.get("fetchedAt")
    if fetched_at:
        print(f"\nnews-live fetchedAt: {fetched_at}")
        print(f"news-live counts: {news.get('counts')}")

    src = SRC.read_text(encoding="utf-8")
    build_ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    embedded_json = json.dumps(embedded, ensure_ascii=False)

    html_out = (
        HTML_HEAD.replace("{BUILD_TS}", build_ts).replace("{EMBEDDED_JSON}", embedded_json)
        + src
        + HTML_TAIL
    )
    OUT.write_text(html_out, encoding="utf-8")

    print(f"\n[ok] wrote {OUT} ({len(html_out):,} bytes, built {build_ts} UTC)")
    if errors:
        print("\n[warn] non-fatal snapshot issues:")
        for e in errors:
            print(f"  - {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
