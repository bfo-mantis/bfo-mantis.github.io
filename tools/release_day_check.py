#!/usr/bin/env python3
"""Release-day check: which releases go live on a date, and whether the site already shows them in release mode.

Usage:
    python3 tools/release_day_check.py [--date YYYY-MM-DD] [--site https://bfo-mantis.github.io/ | --local]

  --date   the release date to check (default: today in America/Phoenix)
  --site   check the live site (default https://bfo-mantis.github.io/; each fetch adds a cache-busting query)
  --local  check the built files in this checkout instead (e.g. after RELEASE_DATE_OVERRIDE=... tools/build_pages.py)

Prints one JSON object and exits 0 when every release going live that day passes every check (or none go live),
1 when something is not in release mode yet, 2 on a fetch/usage error. It never posts anywhere; the Discord
announcement job calls it to decide whether to post.

Checks per release (all read from the static HTML, i.e. what visitors without JS and crawlers see):
  release_page_released  release page: "Released" label shown, "· Upcoming" eyebrow hidden
  store_links            release page: direct store buttons, or the HyperFollow button labelled "Listen" (not "Pre-save")
  home_hero_card         homepage hero card links to the release and shows "Latest release"
  home_featured_card     homepage "Play this now" card is the release, labelled "Latest release"
  rss_item               feed.xml has an <item> linking to the release page
"""
import argparse, json, re, sys, time, urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent

def fetcher(site, local):
    def get(path):
        if local:
            p = ROOT / (path + "index.html" if path.endswith("/") or path == "" else path)
            return p.read_text(encoding="utf-8")
        url = site + path + ("&" if "?" in path else "?") + f"rdc={int(time.time())}"
        req = urllib.request.Request(url, headers={"User-Agent": "bfo-mantis-release-day-check", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8")
    return get

def shown(span_cls, text, html):
    """True when a <span class="span_cls">text</span> exists without the hidden attribute."""
    return re.search(rf'<span class="{span_cls}"(?! hidden)>\s*{re.escape(text)}', html) is not None

def check_release(r, get, home, feed):
    slug = r["slug"]; res = {"slug": slug, "title": r["title"], "release_date": r["release_date"],
                            "isrcs": [t.get("isrc") for t in r.get("tracks", [])]}
    try:
        page = get(f"release/{slug}/")
    except Exception as ex:
        res["error"] = f"release page: {ex}"; res["ok"] = False; return res
    released = shown("js-released", "Released", page) and not shown("js-upcoming", "· Upcoming", page)
    direct = re.findall(r'<a class="store" href="([^"]+)"', page)
    hf = re.search(r'<a class="btn" href="(https://distrokid\.com/hyperfollow/[^"]+)"[^>]*>.*?</a>', page, re.S)
    hf_listen = bool(hf and shown("js-released", "Listen", hf.group(0)) and not shown("js-upcoming", "Pre-save / listen", hf.group(0)))
    res["release_page_released"] = released
    res["store_links"] = bool(direct) or hf_listen
    res["store_link_urls"] = direct or ([hf.group(1)] if hf else [])
    res["store_link_kind"] = "direct" if direct else ("hyperfollow" if hf else "none")
    hero = re.search(r'<a class="hero-latest" href="([^"]+)"[^>]*>(.*?)</a>', home, re.S)
    res["home_hero_card"] = bool(hero and hero.group(1).rstrip("/").endswith(f"release/{slug}") and shown("js-released", "Latest release", hero.group(2)))
    feat = re.search(r'<div class="feat" data-slug="([^"]+)">(.*?)</h3>', home, re.S)
    res["home_featured_card"] = bool(feat and feat.group(1) == slug and re.search(r'<p class="eyebrow"[^>]*>(?:<span class="js-upcoming" hidden>Latest release</span>)?\s*(?:<span class="js-released">)?Latest release', feat.group(2)) is not None)
    res["rss_item"] = feed is not None and re.search(rf"<item>\s*<title>[^<]*</title>\s*<link>[^<]*/release/{re.escape(slug)}/</link>", feed) is not None
    res["ok"] = all(res[k] for k in ("release_page_released", "store_links", "home_hero_card", "home_featured_card", "rss_item"))
    return res

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="YYYY-MM-DD (default: today in America/Phoenix)")
    ap.add_argument("--site", default="https://bfo-mantis.github.io/")
    ap.add_argument("--local", action="store_true")
    a = ap.parse_args()
    d = date.fromisoformat(a.date) if a.date else datetime.now(ZoneInfo("America/Phoenix")).date()
    site = a.site.rstrip("/") + "/"
    get = fetcher(site, a.local)
    out = {"date": d.isoformat(), "checked": "local" if a.local else site,
           "checked_at": datetime.now(ZoneInfo("America/Phoenix")).isoformat(timespec="seconds"), "releases": []}
    try:
        data = json.loads(get("assets/data/releases.json"))
        home = get("")
        try: feed = get("feed.xml")
        except Exception: feed = None
    except Exception as ex:
        out["error"] = str(ex); out["ok"] = False
        print(json.dumps(out, indent=1, ensure_ascii=False)); sys.exit(2)
    going = [r for r in data["releases"] if r["release_date"] == d.isoformat()]
    out["feed_present"] = feed is not None
    out["releases"] = [check_release(r, get, home, feed) for r in going]
    out["going_live"] = [r["slug"] for r in going]
    out["ok"] = all(r["ok"] for r in out["releases"])
    print(json.dumps(out, indent=1, ensure_ascii=False))
    sys.exit(0 if out["ok"] else 1)

if __name__ == "__main__":
    main()
