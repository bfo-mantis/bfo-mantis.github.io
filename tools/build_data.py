#!/usr/bin/env python3
"""Regenerate assets/data/releases.js (+ releases.json) and cover art from the DistroKid catalog,
then (unless --no-pages) the static pages, share images, sitemap etc. via tools/build_pages.py.

Usage (from the site root or anywhere):
    python3 tools/build_data.py [--catalog PATH] [--links PATH] [--skip-covers] [--force-covers]

- Excludes releases whose artist list doesn't include "bfo.mantis" (e.g. LOVELORN by Wetline).
- Optional --links file (list of {title, hyperfollow_url, store_links}) is merged over the catalog,
  so newly collected HyperFollow/store links can be dropped in without editing the catalog.
- Listen link priority: hyperfollow_url > first store link > distrokid_release_page (only if public,
  i.e. not a /dashboard/ or /signin/ URL that requires login) > none (button hidden).
- Covers: downloads original once to tools/.cache/, writes assets/covers/<slug>-800.jpg/.webp and -400.
Requires Pillow (pip install pillow).
"""
import argparse, json, re, sys, unicodedata, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIST = "bfo.mantis"

def slugify(s, used):
    base = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower() or "release"
    slug, i = base, 2
    while slug in used:
        slug, i = f"{base}-{i}", i + 1
    used.add(slug)
    return slug

def is_public(url):
    if not url or not url.startswith("http"):
        return False
    return not re.search(r"distrokid\.com/(dashboard|signin|account)", url)

def pick_listen(r):
    if is_public(r.get("hyperfollow_url")):
        return r["hyperfollow_url"], "hyperfollow"
    sl = r.get("store_links") or {}
    vals = sl.values() if isinstance(sl, dict) else sl
    for v in vals:
        u = v.get("url") if isinstance(v, dict) else v
        if is_public(u):
            return u, "store"
    if is_public(r.get("distrokid_release_page")):
        return r["distrokid_release_page"], "distrokid_page"
    return None, None

STORE_ORDER = ["Spotify", "YouTube Music", "Apple Music", "iTunes", "Amazon", "Deezer", "Tidal", "iHeartRadio"]
STORE_NAMES = {"youtube_music": "YouTube Music"}

def clean_stores(sl, rtype="album"):
    """Return [{name, url}] for public store links only, in a stable order; never adds stores.
    Nested values like youtube_music {"album": playlist, "track": watch} resolve to the track URL
    for singles and the album playlist for albums."""
    if not sl:
        return []
    items = sl.items() if isinstance(sl, dict) else [(x.get("name"), x.get("url")) for x in sl]
    flat = []
    for name, url in items:
        name = STORE_NAMES.get(name, name)
        if isinstance(url, dict):
            url = (url.get("track") or url.get("album")) if rtype == "single" else (url.get("album") or url.get("track"))
        flat.append((name, url))
    items = flat
    out = []
    for name, url in items:
        if not name or not is_public(url):
            continue
        if url.startswith("http://www.amazon.") or url.startswith("http://amazon."):
            url = "https://" + url[len("http://"):]
        out.append({"name": name, "url": url})
    rank = {n: i for i, n in enumerate(STORE_ORDER)}
    return sorted(out, key=lambda x: rank.get(x["name"], len(STORE_ORDER)))

def track_entry(t, lyrics, lstatus):
    isrc = t.get("isrc")
    has = bool(isrc in lyrics and (lyrics[isrc].get("lyrics") or "").strip())
    st = lstatus.get(isrc)
    status = "lyrics" if has else ("instrumental" if st == "instrumental" else "none")
    return {"n": t["n"], "title": t["title"], "isrc": isrc, "lyrics": status}

# Redactions are emitted as structured tokens, never as placeholder text, so the published lyrics files
# contain no searchable marker. Lengths are bucketed so a bar doesn't reveal the exact word length.
_R = "\ue000"   # private-use sentinel used only inside the build

def _bucket(n, whole_line):
    step, lo, hi = (16, 16, 64) if whole_line else (8, 8, 48)
    return max(lo, min(hi, -(-n // step) * step))

def _tok(n, whole_line):
    return f"{_R}{_bucket(n, whole_line)}{_R}"

def structure_lyrics(text):
    """Plain string if the track has no redactions; otherwise a list of lines, each either a string or a list
    of parts where a part is a string or {"r": bucketed_length}. A line made of a single {"r": n} is a
    whole-line redaction."""
    if _R not in text:
        return text
    out = []
    for line in text.split("\n"):
        if _R not in line:
            out.append(line); continue
        parts = []
        for i, chunk in enumerate(line.split(_R)):
            if i % 2:
                parts.append({"r": int(chunk)})
            elif chunk:
                parts.append(chunk)
        out.append(parts)
    return out

def count_redactions(v):
    return 0 if isinstance(v, str) else sum(1 for l in v if isinstance(l, list) for p in l if isinstance(p, dict))

def apply_lyrics_edits(isrc, text, edits, log):
    """Apply content/lyrics_edits.json to one track. Each edit is checked against a hash of the source line."""
    import hashlib
    lines = text.replace("\r\n", "\n").strip("\n").split("\n")
    spec = (edits.get(isrc) or {}).get("edits", [])
    drop = set()
    # spans right-to-left so offsets stay valid
    for e in sorted(spec, key=lambda x: (x["line"], -(x.get("span") or [0])[0])):
        n = e["line"]
        if not 1 <= n <= len(lines):
            log.append(f"{isrc} L{n}: out of range, skipped"); continue
        if hashlib.sha256(lines_src(text)[n - 1].encode()).hexdigest()[:16] != e["line_sha256_16"]:
            log.append(f"{isrc} L{n}: source line changed, edit skipped"); continue
        if e["action"] == "delete_line":
            drop.add(n)
        elif e["action"] == "redact_line":
            lines[n - 1] = _tok(len(lines_src(text)[n - 1].strip()), True)
        elif e["action"] == "redact_span":
            a, b = e["span"]; lines[n - 1] = lines[n - 1][:a] + _tok(b - a, False) + lines[n - 1][b:]
    out = "\n".join(l for i, l in enumerate(lines, 1) if i not in drop)
    out = re.sub(r"\n{3,}", "\n\n", out).strip("\n")
    return structure_lyrics(out)

def lines_src(text):
    return text.replace("\r\n", "\n").strip("\n").split("\n")

def load_overrides(folder):
    """content/lyrics_overrides/<ISRC>.txt: authoritative lyrics from the artist. Used as-is except:
    line endings normalised, section-label lines removed, leading/trailing blank lines trimmed."""
    out = {}
    d = Path(folder)
    if d.is_dir():
        for f in sorted(d.glob("*.txt")):
            text = f.read_text(encoding="utf-8").replace("\r\n", "\n")
            # drop section labels (lines entirely in parentheses or square brackets, e.g. "(Chorus)", "[Verse 1]") for consistency with
            # the other songs; blank lines between sections stay as stanza breaks
            lines = [l.rstrip() for l in text.split("\n") if not re.fullmatch(r"\s*(\(.*\)|\[.*\])\s*", l)]
            out[f.stem.strip().upper()] = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n")
    return out

def write_lyrics_files(releases, lyrics, edits=None, log=None, overrides=None):
    """One small JSON per release (assets/data/lyrics/<slug>.json), fetched only on that release page."""
    d = ROOT / "assets" / "data" / "lyrics"; d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*.json"):
        f.unlink()
    n = 0
    log = log if log is not None else []
    overrides = overrides or {}
    for r in releases:
        m = {}
        for t in r["tracks"]:
            if t["isrc"] in overrides:
                # artist-supplied text replaces the DistroKid text entirely; lyrics_edits.json is not applied
                t["lyrics"] = "lyrics"; t["lyrics_source"] = "artist"
                m[t["isrc"]] = overrides[t["isrc"]]
                if (edits or {}).get(t["isrc"]):
                    log.append(f"{t['isrc']}: override present, {len(edits[t['isrc']]['edits'])} lyrics_edits entries skipped")
            elif t["lyrics"] == "lyrics":
                m[t["isrc"]] = apply_lyrics_edits(t["isrc"], lyrics[t["isrc"]]["lyrics"], edits or {}, log)
        r["lyrics_file"] = f"assets/data/lyrics/{r['slug']}.json" if m else None
        if m:
            (d / f"{r['slug']}.json").write_text(json.dumps(m, ensure_ascii=False)); n += 1
    return n

def make_covers(url, slug, force):
    from PIL import Image
    cache = ROOT / "tools" / ".cache"; cache.mkdir(parents=True, exist_ok=True)
    out = ROOT / "assets" / "covers"; out.mkdir(parents=True, exist_ok=True)
    raw = cache / f"{slug}.orig"
    if force or not raw.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw.write_bytes(resp.read())
    im = Image.open(raw).convert("RGB")
    sizes = {}
    for size in (800, 400):
        t = im.copy()
        if t.width > size:
            t = t.resize((size, round(t.height * size / t.width)), Image.LANCZOS)
        t.save(out / f"{slug}-{size}.jpg", "JPEG", quality=82, optimize=True, progressive=True)
        t.save(out / f"{slug}-{size}.webp", "WEBP", quality=78, method=6)
        sizes[size] = (t.width, t.height)
    return {"jpg": f"assets/covers/{slug}-800.jpg", "webp": f"assets/covers/{slug}-800.webp",
            "jpg_small": f"assets/covers/{slug}-400.jpg", "webp_small": f"assets/covers/{slug}-400.webp",
            "width": sizes[800][0], "height": sizes[800][1], "original_size": list(im.size)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="/workspace/bfo_mantis_catalog.json")
    ap.add_argument("--links", default=None, help="optional JSON list of link overrides keyed by title")
    ap.add_argument("--lyrics", default="/workspace/bfo_mantis_lyrics.json",
                    help="JSON keyed by ISRC: {release_title, track_title, lyrics}; skipped if missing")
    ap.add_argument("--lyrics-status", default="/workspace/lyrics_status.json",
                    help="JSON keyed by ISRC: has_lyrics | instrumental | no_lyrics; skipped if missing")
    ap.add_argument("--site-url", default="https://bfo-mantis.github.io/", help="absolute URL used for canonical/Open Graph/sitemap")
    ap.add_argument("--no-pages", action="store_true", help="only write data; skip tools/build_pages.py")
    ap.add_argument("--lyrics-overrides", default=str(ROOT / "content" / "lyrics_overrides"),
                    help="folder of <ISRC>.txt files that fully replace the DistroKid lyrics for that track")
    ap.add_argument("--lyrics-edits", default=str(ROOT / "content" / "lyrics_edits.json"),
                    help="line-level cleanup/redaction edits keyed by ISRC (applied at build time; source untouched)")
    ap.add_argument("--skip-covers", action="store_true")
    ap.add_argument("--force-covers", action="store_true")
    a = ap.parse_args()
    cat = json.loads(Path(a.catalog).read_text())
    overrides = {}
    if a.links and Path(a.links).exists():
        for o in json.loads(Path(a.links).read_text()):
            overrides[o["title"]] = o
    lyrics = json.loads(Path(a.lyrics).read_text()) if a.lyrics and Path(a.lyrics).exists() else {}
    lstatus = json.loads(Path(a.lyrics_status).read_text()) if a.lyrics_status and Path(a.lyrics_status).exists() else {}
    used, releases, excluded, failed = set(), [], [], []
    for r in cat:
        if ARTIST not in (r.get("artist") or []):
            excluded.append(f'{r["title"]} ({", ".join(r.get("artist") or [])})'); continue
        o = overrides.get(r["title"], {})
        for k in ("hyperfollow_url", "store_links"):
            if o.get(k): r[k] = o[k]
        slug = slugify(r["title"], used)
        d = datetime.strptime(r["release_date"], "%B %d, %Y").date()
        url, src = pick_listen(r)
        cover = None
        if not a.skip_covers:
            try:
                cover = make_covers(r["cover_art_url"], slug, a.force_covers)
            except Exception as e:
                failed.append(f'{r["title"]}: {e}')
        else:
            p = ROOT / "assets" / "covers" / f"{slug}-800.jpg"
            if p.exists():
                cover = {"jpg": f"assets/covers/{slug}-800.jpg", "webp": f"assets/covers/{slug}-800.webp",
                         "jpg_small": f"assets/covers/{slug}-400.jpg", "webp_small": f"assets/covers/{slug}-400.webp",
                         "width": 800, "height": 800}
        releases.append({
            "slug": slug, "title": r["title"], "artist": r["artist"], "type": r["type"].lower(),
            "release_date": d.isoformat(), "release_date_display": r["release_date"],
            "genre": r.get("genre"), "label": r.get("label"), "upc": r.get("upc"),
            "listen_url": url, "listen_source": src,
            "store_links": clean_stores(r.get("store_links"), r["type"].lower()), "cover": cover,
            "tracks": [track_entry(t, lyrics, lstatus) for t in r["tracklist"]],
        })
    # newest first; stable for equal dates (keeps catalog order)
    releases.sort(key=lambda x: x["release_date"], reverse=True)
    edits = json.loads(Path(a.lyrics_edits).read_text()).get("tracks", {}) if a.lyrics_edits and Path(a.lyrics_edits).exists() else {}
    edit_log = []
    overrides = load_overrides(a.lyrics_overrides) if a.lyrics_overrides else {}
    nfiles = write_lyrics_files(releases, lyrics, edits, edit_log, overrides)
    site_isrcs_o = {t["isrc"] for x in releases for t in x["tracks"]}
    print(f"lyrics overrides: {len(overrides)} applied" + (f"; NOT on site: {sorted(set(overrides) - site_isrcs_o)}" if set(overrides) - site_isrcs_o else ""))
    n_ed = sum(len(v["edits"]) for v in edits.values())
    site_isrcs = {t["isrc"] for x in releases for t in x["tracks"]}
    data = {"artist": ARTIST, "generated": datetime.now().isoformat(timespec="seconds"), "releases": releases}
    out = ROOT / "assets" / "data"; out.mkdir(parents=True, exist_ok=True)
    js = json.dumps(data, ensure_ascii=False, indent=1)
    (out / "releases.json").write_text(js)
    (out / "releases.js").write_text("// Generated by tools/build_data.py - do not edit by hand.\nwindow.BFO_DATA = " + js + ";\n")
    albums = sum(1 for x in releases if x["type"] == "album"); singles = sum(1 for x in releases if x["type"] == "single")
    print(f"releases: {len(releases)} (albums {albums}, singles {singles})")
    print("excluded:", excluded or "none")
    print("listen sources:", {s: sum(1 for x in releases if x["listen_source"] == s) for s in ("hyperfollow", "store", "distrokid_page", None)})
    print("with store buttons:", sum(1 for x in releases if x["store_links"]))
    from collections import Counter
    print("stores:", dict(Counter(st["name"] for x in releases for st in x["store_links"])))
    from collections import Counter as _C
    print("track lyrics:", dict(_C(t["lyrics"] for x in releases for t in x["tracks"])), "| lyrics files:", nfiles)
    print("lyrics ISRCs not on site:", [k for k in lyrics if k not in site_isrcs] or "none")
    print("status ISRCs not on site:", [k for k in lstatus if k not in site_isrcs] or "none")
    print("site ISRCs missing from status:", [k for k in site_isrcs if lstatus and k not in lstatus] or "none")
    print(f"lyrics edits: {n_ed} in {len(edits)} tracks | problems:", edit_log or "none")
    print("cover failures:", failed or "none")
    if not a.no_pages:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build_pages
        build_pages.main(a.site_url)
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
