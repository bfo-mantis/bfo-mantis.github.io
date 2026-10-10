#!/usr/bin/env python3
"""Generate the static HTML pages, share images, icons, sitemap and robots.txt from
assets/data/releases.json (which tools/build_data.py writes from the catalog).

Run automatically at the end of tools/build_data.py, or on its own:
    python3 tools/build_pages.py [--site-url https://bfo-mantis.github.io/]

Outputs (all GENERATED, all links relative so the site also works from a sub-path):
  index.html                     home (pre-rendered: hero, Songs and Instrumentals, each with albums + singles, optional About)
  release/<slug>/index.html      one static page per release (title, meta, Open Graph, JSON-LD)
  release.html                   tiny redirect so old release.html?r=<slug> links keep working
  404.html                       self-contained "not found" page
  sitemap.xml, robots.txt, site.webmanifest, favicon.svg/.ico, apple-touch-icon.png, assets/img/icon-*.png
  assets/img/hero-*.{webp,jpg}   pre-blurred cover collage for the hero (one image instead of 24)
  assets/img/og/*.jpg            1200x630 share images (home + one per release)
Lyrics are never written into HTML, JSON-LD or the sitemap; release pages fetch them on demand.
"""
import argparse, hashlib, html, json, math, re, unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "tools" / "fonts"
ARTIST = "bfo.mantis"
LABEL_NAME = "bfo.mantis Records"
COPY_YEAR = 2026   # site-wide footer notice (user-approved wording)
YTM_ARTIST = "https://music.youtube.com/channel/UCAr9yfuSAyMs5B2Iycvr7-Q"
BG, ACCENT, TEXT, MUTED = (11, 11, 15), (200, 255, 77), (236, 235, 242), (163, 162, 179)

e = lambda s: html.escape(str(s if s is not None else ""), quote=True)

def short_date(iso):
    d = date.fromisoformat(iso)
    return d.strftime("%b ") + str(d.day) + d.strftime(", %Y")

def asset_hash(*paths):
    h = hashlib.sha1()
    for p in paths:
        h.update((ROOT / p).read_bytes())
    return h.hexdigest()[:8]

# ---------------------------------------------------------------- images
def _font(name, size, weight):
    from PIL import ImageFont
    f = ImageFont.truetype(str(FONTS / name), size)
    try:
        f.set_variation_by_axes([weight] if name.startswith("Syne") else [min(32, max(14, size)), weight])
    except Exception:
        pass
    return f

CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

def _draw_text(d, xy, text, font, fill, cjk_size=None):
    """Draw text; characters outside Latin ranges fall back to a CJK font if one is installed."""
    from PIL import ImageFont
    x, y = xy
    fb = None
    for ch in text:
        f = font
        if ord(ch) > 0x2E7F:
            if fb is None:
                try: fb = ImageFont.truetype(CJK, cjk_size or font.size, index=2)
                except Exception: fb = font
            f = fb
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch)
    return x

def _text_w(text, font, cjk_size=None):
    from PIL import ImageFont
    w = 0
    for ch in text:
        if ord(ch) > 0x2E7F:
            try: w += ImageFont.truetype(CJK, cjk_size or font.size, index=2).getlength(ch)
            except Exception: w += font.getlength(ch)
        else:
            w += font.getlength(ch)
    return w

def _wrap(text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if _text_w(t, font) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def _cover(r, size="jpg"):
    from PIL import Image
    p = ROOT / r["cover"][size] if r.get("cover") else None
    return Image.open(p).convert("RGB") if p and p.exists() else None

def collage(releases, W, H, cols, tile_px=400):
    """Rotated grid of cover art, softly blurred and darkened (baked in, so the browser loads one image)."""
    from PIL import Image, ImageFilter, ImageEnhance
    imgs = [c for c in (_cover(r, "jpg_small") for r in releases) if c is not None]
    if not imgs:
        return Image.new("RGB", (W, H), BG)
    tile = math.ceil(W * 1.25 / cols)
    rows = math.ceil(H * 1.35 / tile) + 1
    big = Image.new("RGB", (tile * cols, tile * rows), BG)
    for i in range(cols * rows):
        big.paste(imgs[i % len(imgs)].resize((tile, tile), Image.LANCZOS), ((i % cols) * tile, (i // cols) * tile))
    big = big.rotate(4, resample=Image.BICUBIC, expand=False, fillcolor=BG)
    l, t = (big.width - W) // 2, (big.height - H) // 2
    out = big.crop((l, t, l + W, t + H)).filter(ImageFilter.GaussianBlur(max(1.5, W / 800)))
    out = ImageEnhance.Color(out).enhance(.9)
    return ImageEnhance.Brightness(out).enhance(.42)

def _gradient_overlay(im, strength=.92):
    """Darken bottom-left like the site hero so text stays readable."""
    from PIL import Image
    W, H = im.size
    mask = Image.new("L", (W, H))
    px = mask.load()
    for y in range(0, H):
        for x in range(0, W, 4):
            dx, dy = x / W, 1 - y / H
            v = int(255 * strength * max(0, 1 - math.hypot(dx * .85, dy * 1.1)))
            for k in range(4):
                if x + k < W: px[x + k, y] = v
    return Image.composite(Image.new("RGB", (W, H), BG), im, mask)

def build_images(releases, stats):
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
    img = ROOT / "assets" / "img"; (img / "og").mkdir(parents=True, exist_ok=True)
    for f in (img / "og").glob("*.jpg"):
        f.unlink()
    released = [r for r in releases if r.get("cover")]
    # hero (desktop + mobile)
    for name, W, H, cols in (("hero-1600", 1600, 900, 6), ("hero-800", 800, 1000, 3)):
        h = collage(released, W, H, cols)
        h.save(img / f"{name}.webp", "WEBP", quality=62, method=6)
        h.save(img / f"{name}.jpg", "JPEG", quality=70, optimize=True, progressive=True)
    # default share image
    W, H = 1200, 630
    og = _gradient_overlay(collage(released, W, H, 6))
    d = ImageDraw.Draw(og)
    size = 150
    while _font("Syne.ttf", size, 800).getlength("bfo.mantis") > W - 150:
        size -= 2
    f = _font("Syne.ttf", size, 800); ty = 500 - int(size * 1.15)
    x = _draw_text(d, (70, ty), "bfo", f, TEXT)
    x = _draw_text(d, (x, ty), ".", f, ACCENT)
    _draw_text(d, (x, ty), "mantis", f, TEXT)
    _draw_text(d, (76, 520), stats, _font("Inter.ttf", 34, 500), MUTED)
    og.save(img / "og" / "home.jpg", "JPEG", quality=84, optimize=True, progressive=True)
    # one share image per release
    for r in releases:
        c = _cover(r)
        if c is None:
            continue
        bg = c.resize((W, W), Image.LANCZOS).crop((0, (W - H) // 2, W, (W - H) // 2 + H))
        bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(48))).enhance(.33)
        cs = 470
        sh = Image.new("RGBA", (cs + 80, cs + 80), (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((40, 50, cs + 40, cs + 50), 26, fill=(0, 0, 0, 190))
        bg.paste(sh.filter(ImageFilter.GaussianBlur(22)), (40, 40), sh.filter(ImageFilter.GaussianBlur(22)))
        m = Image.new("L", (cs, cs)); ImageDraw.Draw(m).rounded_rectangle((0, 0, cs, cs), 22, fill=255)
        bg.paste(c.resize((cs, cs), Image.LANCZOS), (80, 80), m)
        d = ImageDraw.Draw(bg)
        x0, maxw = 610, W - 610 - 60
        _draw_text(d, (x0, 112), ("ALBUM" if r["type"] == "album" else "SINGLE"), _font("Inter.ttf", 26, 700), ACCENT)
        size = 76
        while True:
            tf = _font("Syne.ttf", size, 800)
            lines = _wrap(r["title"], tf, maxw)
            if (len(lines) <= 3 and all(_text_w(l, tf) <= maxw for l in lines)) or size <= 40:
                break
            size -= 4
        y = 160
        for l in lines:
            _draw_text(d, (x0, y), l, tf, TEXT); y += int(size * 1.08)
        y += 22
        _draw_text(d, (x0, y), ARTIST, _font("Inter.ttf", 34, 600), TEXT)
        meta = " · ".join(x for x in [r["release_date_display"], r.get("genre")] if x)
        _draw_text(d, (x0, y + 50), meta, _font("Inter.ttf", 28, 500), MUTED)
        n = len(r["tracks"])
        if r["type"] == "album":
            _draw_text(d, (x0, y + 90), f"{n} track{'s' if n != 1 else ''}", _font("Inter.ttf", 28, 500), MUTED)
        bg.save(img / "og" / f"{r['slug']}.jpg", "JPEG", quality=84, optimize=True, progressive=True)
    # one share image per genre: collage of that genre's covers + the genre name
    for g, rs in genre_groups(releases):
        og = _gradient_overlay(collage([r for r in rs if r.get("cover")], W, H, 6))
        d = ImageDraw.Draw(og)
        _draw_text(d, (74, 300), "GENRE", _font("Inter.ttf", 28, 700), ACCENT)
        size = 120
        while _text_w(g, _font("Syne.ttf", size, 800)) > W - 150 and size > 50:
            size -= 4
        _draw_text(d, (70, 342), g, _font("Syne.ttf", size, 800), TEXT)
        nt = sum(len(r["tracks"]) for r in rs)
        _draw_text(d, (76, 520), f"{ARTIST} · {len(rs)} release{'s' if len(rs) != 1 else ''} · {nt} tracks", _font("Inter.ttf", 34, 500), MUTED)
        og.save(img / "og" / f"genre-{genre_slug(g)}.jpg", "JPEG", quality=84, optimize=True, progressive=True)
    # icons: favicon = the accent dot from the wordmark; app icons = the full "bfo.mantis" wordmark
    def wordmark_icon(S):
        im = Image.new("RGB", (S, S), BG); d = ImageDraw.Draw(im)
        size = int(S * .2)
        f = _font("Syne.ttf", size, 800)
        w = f.getlength("bfo.mantis")
        while w > S * .84:
            size -= 1; f = _font("Syne.ttf", size, 800); w = f.getlength("bfo.mantis")
        x = (S - w) / 2; y = S / 2 - size * .62
        x = _draw_text(d, (x, y), "bfo", f, TEXT); x = _draw_text(d, (x, y), ".", f, ACCENT); _draw_text(d, (x, y), "mantis", f, TEXT)
        return im
    for S, path in ((180, ROOT / "apple-touch-icon.png"), (192, img / "icon-192.png"), (512, img / "icon-512.png")):
        wordmark_icon(S).save(path, "PNG", optimize=True)
    def dot_icon(S):
        im = Image.new("RGBA", (S * 4, S * 4), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, S * 4 - 1, S * 4 - 1), int(S * 4 * .22), fill=BG + (255,))
        r = S * 4 * .2; cx, cy = S * 2, S * 2
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ACCENT + (255,))
        return im.resize((S, S), Image.LANCZOS)
    dot_icon(48).save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    (ROOT / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#0b0b0f"/>'
        '<circle cx="32" cy="32" r="12.8" fill="#c8ff4d"/></svg>\n')

# ---------------------------------------------------------------- html pieces
def word_fit(title):
    """Width (in em) of the longest word in Syne 800 incl. the h1's -0.035em tracking, so CSS can shrink the
    title until that word fits on one line instead of breaking mid-word (used as --fit on the release h1)."""
    try:
        f = _font("Syne.ttf", 100, 800)
        w = max((f.getlength(x) / 100 - .035 * len(x)) for x in title.split()) if title.split() else 1
        return round(w * 1.04, 3)
    except Exception:
        return 0

def picture(root, r, sizes, eager=False, alt=None, big=False):
    c = r.get("cover")
    if not c:
        return '<div class="noart" aria-hidden="true"></div>'
    alt = f"Cover art for {r['title']} by {ARTIST}" if alt is None else alt
    load = ' fetchpriority="high"' if eager else ' loading="lazy" decoding="async"'
    w = 800 if big else 400
    return (f'<picture><source type="image/webp" srcset="{root}{c["webp_small"]} 400w, {root}{c["webp"]} 800w" sizes="{sizes}">'
            f'<img src="{root}{c["jpg" if big else "jpg_small"]}" srcset="{root}{c["jpg_small"]} 400w, {root}{c["jpg"]} 800w" sizes="{sizes}" '
            f'width="{w}" height="{w}" alt="{e(alt)}"{load}></picture>')

def updown(r, today):
    up = date.fromisoformat(r["release_date"]) > today
    return up, ("" if up else " hidden"), (" hidden" if up else "")

def genre_slug(g):
    """'Hip Hop/Rap' -> 'hip-hop-rap', 'Christian/Gospel' -> 'christian-gospel'."""
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", g).encode("ascii", "ignore").decode().lower()).strip("-") or "other"

def genre_groups(releases):
    """[(genre, releases newest first)], most releases first, then by name. Releases without a genre are skipped."""
    groups = {}
    for r in releases:
        if r.get("genre"): groups.setdefault(r["genre"], []).append(r)
    return sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0].lower()))

def genre_href(root, g):
    return f"{root}genre/{genre_slug(g)}/"

def genre_link(root, g, cls="glink"):
    return f'<a class="{cls}" href="{genre_href(root, g)}">{e(g)}</a>'

def card(root, r, sizes, today, eager=False):
    # The genre is its own link, so it sits outside the card link (no nested <a>).
    n = len(r["tracks"])
    sub = (f"{n} track{'s' if n != 1 else ''} · " if r["type"] == "album" else "") + short_date(r["release_date"]) + (f" · {genre_link(root, r['genre'])}" if r.get("genre") else "")
    up, hid_up, _ = updown(r, today)
    badge = f'<span class="badge js-upcoming"{hid_up}>Out {short_date(r["release_date"]).rsplit(",", 1)[0]}</span>'
    return (f'<li class="card" data-date="{r["release_date"]}"><a class="card-link" href="{root}release/{r["slug"]}/">'
            f'<div class="art">{picture(root, r, sizes, eager, alt="")}{badge}</div>'
            f'<div class="info"><h3 class="title">{e(r["title"])}</h3></div></a><p class="sub">{sub}</p></li>')

CATS = (("vocal", "songs", "Songs"), ("instrumental", "instrumentals", "Instrumentals"))
def cat_anchor(r):
    return "songs" if r.get("category", "vocal") == "vocal" else "instrumentals"

def track_counts(releases):
    """Tracks with lyrics count as songs; instrumental-marked tracks and tracks on instrumental releases as instrumentals."""
    songs = sum(1 for r in releases for t in r["tracks"] if t["lyrics"] == "lyrics")
    return songs, sum(len(r["tracks"]) for r in releases) - songs

def cat_sections_html(root, releases, today, eager_albums=4):
    """Songs / Instrumentals sections, each with Albums and Singles sub-grids (empty groups hidden), newest first."""
    eager_left = [eager_albums]
    def sub_grid(anchor, rs, kind):
        if not rs: return ""
        plural = f"{kind.lower()}s"
        if kind == "Album":
            items = "".join(card(root, r, ALBUM_SIZES, today, eager_left[0] > i) for i, r in enumerate(rs))
            eager_left[0] = 0
        else:
            items = "".join(card(root, r, SINGLE_SIZES, today) for r in rs)
        return f'''
    <section class="subsection" id="{anchor}-{plural}" aria-labelledby="{anchor}-{plural}-title">
      <div class="sub-head"><h3 id="{anchor}-{plural}-title">{kind}s</h3><p class="count">{len(rs)} {plural if len(rs) != 1 else kind.lower()}</p></div>
      <ul class="grid grid-{plural}">
        {items}
      </ul>
    </section>'''
    out = ""
    for cat, anchor, label in CATS:
        rs = [r for r in releases if r.get("category", "vocal") == cat]
        if not rs: continue
        ns, ni = track_counts(rs)
        nt = ns if cat == "vocal" else ni
        out += f'''
  <section id="{anchor}" class="section cat-section" aria-labelledby="{anchor}-title">
    <div class="section-head">
      <h2 id="{anchor}-title">{label}</h2>
      <p class="count">{len(rs)} release{"s" if len(rs) != 1 else ""} · {nt} track{"s" if nt != 1 else ""}</p>
    </div>{sub_grid(anchor, [r for r in rs if r["type"] == "album"], "Album")}{sub_grid(anchor, [r for r in rs if r["type"] == "single"], "Single")}
  </section>
'''
    return out

ALBUM_SIZES = "(max-width: 520px) 46vw, (max-width: 1240px) 24vw, 280px"
SINGLE_SIZES = "(max-width: 520px) 46vw, (max-width: 1240px) 16vw, 190px"

GOATCOUNTER = None   # set by main() from content/site_config.json (goatcounter_code); None = no analytics at all

def goatcounter_tag():
    if not GOATCOUNTER: return ""
    return f'\n<script data-goatcounter="https://{GOATCOUNTER}.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'

def head(root, *, title, desc, url, og_image, og_alt, og_type="website", extra="", noindex=False, css_v="", jsonld=None):
    j = f'\n<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False, separators=(",", ":"))}</script>' if jsonld else ""
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>document.documentElement.classList.add("js")</script>
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{'<meta name="robots" content="noindex">' if noindex else f'<link rel="canonical" href="{e(url)}">'}
<meta name="theme-color" content="#0b0b0f">
<meta name="color-scheme" content="dark">
<meta property="og:site_name" content="{ARTIST}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(og_image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{e(og_alt)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{e(og_image)}">
<meta name="twitter:image:alt" content="{e(og_alt)}">{extra}
<link rel="icon" href="{root}favicon.ico" sizes="48x48">
<link rel="icon" href="{root}favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{root}apple-touch-icon.png">
<link rel="manifest" href="{root}site.webmanifest">
<link rel="preload" href="{root}assets/fonts/syne-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{root}assets/fonts/inter-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{root}css/style.css?v={css_v}">{j}{goatcounter_tag()}
</head>'''

HAS_MERCH = False   # set by main() when content/merch.json has items (Merch page + nav link)

def topbar(root, has_about, home=False, current=None):
    p = "" if home else root
    about = f'<a href="{p}#about">About</a>' if has_about else ""
    cur = lambda k: ' aria-current="page"' if current == k else ""
    merch = f'<a href="{root}merch/"{cur("merch")}>Merch</a>' if HAS_MERCH else ""
    return f'''<a class="skip" href="#main">Skip to content</a>
<header class="topbar" id="top">
  <a class="brand" href="{root or './'}" aria-label="{ARTIST} home">bfo<span>.</span>mantis</a>
  <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-nav"><span class="bars" aria-hidden="true"></span>Menu</button>
  <nav id="site-nav" aria-label="Primary">
    <a href="{p}#songs">Songs</a>
    <a href="{p}#instrumentals">Instrumentals</a>
    <a href="{root}genres/"{cur("genres")}>Genres</a>
    {about}
    <a href="{p}#support">Support</a>
    <a href="{root}lounge/"{cur("lounge")}>Lounge</a>{merch}
  </nav>
</header>'''

def footer(root, js_v):
    year = date.today().year
    return f'''<footer class="footer">
  <p>Music, lyrics, artwork and audio previews &copy; {COPY_YEAR} {LABEL_NAME}. All rights reserved.</p>
  <a class="footer-link" href="{root}press/">Press kit</a>
  <a class="footer-top" href="#top">Back to top <span aria-hidden="true">↑</span></a>
</footer>
<a class="to-top" href="#top" aria-label="Back to top"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5l-7 7m7-7l7 7M12 5v14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></a>
<script src="{root}js/app.js?v={js_v}" defer></script>
</body>
</html>
'''

PLAY_ICON = '<svg class="i-play" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z" fill="currentColor"/></svg>'
PAUSE_ICON = '<svg class="i-pause" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor"/></svg>'
NT = '<span class="sr-only"> (opens in a new tab)</span>'
EXT = '<svg class="ext" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'

def buy_html(url, label, tag_id, event=None):
    """Future direct download / donation. A real link only when content/site_config.json supplies an https URL
    (validated in build_data.py); otherwise a disabled, non-clickable placeholder with a "Coming soon" tag."""
    if url:
        gc = f' data-gc="{e(event)}"' if event else ""
        return f'<div class="buy"><a class="btn-alt" href="{e(url)}" target="_blank" rel="noopener"{gc}>{label}{NT}</a></div>'
    return (f'<div class="buy"><button type="button" class="btn-alt" disabled aria-disabled="true" aria-describedby="{tag_id}">{label}</button>'
            f'<span class="soon-tag" id="{tag_id}">Coming soon</span></div>')

def about_html():
    p = ROOT / "content" / "about.html"
    if not p.exists():
        return ""
    body = re.sub(r"<!--.*?-->", "", p.read_text(), flags=re.S).strip()
    return body

def music_group(site):
    return {"@type": "MusicGroup", "name": ARTIST, "url": site, "sameAs": [YTM_ARTIST]}

def release_jsonld(r, site):
    url = f"{site}release/{r['slug']}/"
    d = {"@context": "https://schema.org", "@type": "MusicAlbum", "@id": url + "#release", "name": r["title"], "url": url,
         "byArtist": music_group(site), "datePublished": r["release_date"],
         "albumReleaseType": "https://schema.org/" + ("AlbumRelease" if r["type"] == "album" else "SingleRelease"),
         "albumProductionType": "https://schema.org/StudioAlbum",
         "numTracks": len(r["tracks"]),
         "track": {"@type": "ItemList", "numberOfItems": len(r["tracks"]), "itemListElement": [
             {"@type": "ListItem", "position": t["n"], "item": {"@type": "MusicRecording", "name": t["title"],
              **({"isrcCode": t["isrc"]} if t.get("isrc") else {}), "byArtist": {"@type": "MusicGroup", "name": ARTIST}}}
             for t in r["tracks"]]}}
    if r.get("genre"): d["genre"] = r["genre"]
    if r.get("cover"):
        d["image"] = {"@type": "ImageObject", "contentUrl": site + r["cover"]["jpg"], "url": site + r["cover"]["jpg"],
                      "width": r["cover"].get("width", 800), "height": r["cover"].get("height", 800),
                      "caption": f"Cover art for {r['title']} by {ARTIST}",
                      "copyrightHolder": {"@type": "Organization", "name": LABEL_NAME},
                      "copyrightYear": int(r["release_date"][:4]),
                      "copyrightNotice": f"Artwork © {r['release_date'][:4]} {LABEL_NAME}. All rights reserved.",
                      "creditText": LABEL_NAME}
    if r.get("label"): d["recordLabel"] = {"@type": "Organization", "name": r["label"]}
    if r.get("blurb"): d["description"] = r["blurb"]
    d["copyrightHolder"] = {"@type": "Organization", "name": LABEL_NAME}
    d["copyrightYear"] = int(r["release_date"][:4])
    # sameAs: one canonical URL per store (iTunes is the same Apple page as Apple Music; affiliate/tracking params
    # dropped where the URL works without them). The visible buttons keep the links exactly as listed.
    def canon(u):
        return u.split("?")[0].rstrip("/") if re.match(r"https://(music\.apple\.com|www\.amazon\.com)/", u) else u
    same = list(dict.fromkeys(canon(s["url"]) for s in r.get("store_links") or [] if s["name"] != "iTunes"))
    if same: d["sameAs"] = same
    return d

def article(phrase):
    """'a' or 'an' by sound: vowels, and numbers read with a leading vowel sound (8, 11, 18, 80-89, 800-899, 8000...)."""
    w = phrase.strip().split(" ")[0].split("-")[0]
    if w[:1].isdigit():
        d = "".join(ch for ch in w if ch.isdigit())
        n = int(d)
        lead = n
        while lead >= 1000: lead //= 1000          # 18,000 -> 18; 8,500,000 -> 8
        an = str(lead)[0] == "8" or lead in (11, 18)
    else:
        lw = w.lower()
        an = lw[:1] in "aeiou" and not lw.startswith(("uni", "use", "usu", "eu", "one"))
    return "an" if an else "a"

def short_blurb(b, limit=230):
    """Meta description from a blurb: whole sentences up to ~limit chars (always at least the first sentence)."""
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", b.strip())
    out = sents[0]
    for x in sents[1:]:
        if len(out) + 1 + len(x) > limit: break
        out += " " + x
    return out

def describe(r):
    if r.get("blurb"):
        return short_blurb(r["blurb"])
    n = len(r["tracks"])
    g = (r['genre'] + ' ' if r.get('genre') else '') + ('instrumental ' if r.get("category") == "instrumental" else '')
    body = f"{n}-track {g}album" if r["type"] == "album" else f"{g}single"
    kind = f"{article(body)} {body}"
    s = f"{r['title']}, {kind} by {ARTIST}, released {r['release_date_display']}" + (f" on {r['label']}" if r.get("label") else "") + "."
    stores = [x["name"] for x in r.get("store_links") or []]
    if stores:
        s += " Listen on " + ", ".join(stores[:3]) + (" and more." if len(stores) > 3 else ".")
    elif r.get("listen_url"):
        s += " Listen now."
    return s

# ---------------------------------------------------------------- pages
def build_home(releases, site, today, v, has_about, about, donate_url=None):
    root = ""
    albums = [r for r in releases if r["type"] == "album"]
    singles = [r for r in releases if r["type"] == "single"]
    ntr = sum(len(r["tracks"]) for r in releases)
    n_songs, n_instr = track_counts(releases)
    genres = []
    for r in releases:
        if r.get("genre") and r["genre"] not in genres: genres.append(r["genre"])
    desc = (f"Songs and instrumentals by {ARTIST}: {len(albums)} albums and {len(singles)} singles"
            f" ({', '.join(genres[:5])}{' and more' if len(genres) > 5 else ''}), released on bfo.mantis Records.")
    latest = releases[0]
    up, hid_up, hid_rel = updown(latest, today)
    ld = {"@context": "https://schema.org", **music_group(site),
          "album": [{"@type": "MusicAlbum", "name": r["title"], "url": f"{site}release/{r['slug']}/", "datePublished": r["release_date"]} for r in releases]}
    hd = head(root, title=f"{ARTIST} — Songs & Instrumentals", desc=desc, url=site, og_image=site + "assets/img/og/home.jpg",
              og_alt=f"{ARTIST} wordmark over a collage of cover art", og_type="music.musician" if False else "website",
              css_v=v["css"], jsonld=ld,
              extra=f'\n<link rel="preload" as="image" href="assets/img/hero-1600.webp" media="(min-width: 601px)" fetchpriority="high">'
                    f'\n<link rel="preload" as="image" href="assets/img/hero-800.webp" media="(max-width: 600px)" fetchpriority="high">')
    cat_sections = cat_sections_html(root, releases, today)
    about_sec = (f'''
  <section id="about" class="section about" aria-labelledby="about-title">
    <div class="section-head"><h2 id="about-title">About</h2></div>
    <div class="about-body">{about}</div>
  </section>''' if has_about else "")
    page = f'''{hd}
<body class="home">
{topbar(root, has_about, home=True)}

<main id="main">
  <section class="hero" aria-labelledby="hero-title">
    <picture class="hero-bg" aria-hidden="true">
      <source media="(max-width: 600px)" type="image/webp" srcset="assets/img/hero-800.webp">
      <source media="(max-width: 600px)" srcset="assets/img/hero-800.jpg">
      <source type="image/webp" srcset="assets/img/hero-1600.webp">
      <img src="assets/img/hero-1600.jpg" alt="" width="1600" height="900" fetchpriority="high" decoding="async">
    </picture>
    <div class="hero-inner">
      <p class="eyebrow">Artist · bfo.mantis Records</p>
      <h1 id="hero-title">bfo<span>.</span>mantis</h1>
      <p class="hero-meta"><span>{n_songs} songs · {n_instr} instrumentals · {len(releases)} releases</span>
        <a class="artist-link" href="{YTM_ARTIST}" target="_blank" rel="noopener">YouTube Music{EXT}{NT}</a></p>
      <a class="hero-latest" href="release/{latest['slug']}/" data-date="{latest['release_date']}">
        {picture(root, latest, "84px", eager=True, alt="")}
        <span class="hl-text"><span class="k"><span class="js-released"{hid_rel}>Latest release</span><span class="js-upcoming"{hid_up}>Out {short_date(latest['release_date'])}</span></span>
        <span class="t">{e(latest['title'])}</span>
        <span class="s">{'Album' if latest['type'] == 'album' else 'Single'}{(' · ' + e(latest['genre'])) if latest.get('genre') else ''}</span></span>
        <svg class="chev" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </a>
    </div>
  </section>

{cat_sections}{about_sec}

  <section id="support" class="section support" aria-labelledby="support-title">
    <div class="section-head"><h2 id="support-title">Support bfo.mantis</h2></div>
    <p class="support-line">bfo.mantis is a small independent artist. Direct support is coming soon.</p>
    {buy_html(donate_url, "Donate", "donate-soon", "event/donate")}
  </section>
</main>

{footer(root, v["js"])}'''
    (ROOT / "index.html").write_text(page)

def build_release(releases, i, site, today, v, has_about):
    r = releases[i]
    root = "../../"
    url = f"{site}release/{r['slug']}/"
    up, hid_up, hid_rel = updown(r, today)
    desc = describe(r)
    kind = "Album" if r["type"] == "album" else "Single"
    og_img = site + f"assets/img/og/{r['slug']}.jpg" if r.get("cover") else site + "assets/img/og/home.jpg"
    extra = f'\n<meta property="music:release_date" content="{r["release_date"]}">'
    hd = head(root, title=f"{r['title']} — {ARTIST}", desc=desc, url=url, og_image=og_img,
              og_alt=f"Cover art for {r['title']} by {ARTIST}", og_type="music.album" if r["type"] == "album" else "music.song",
              extra=extra, css_v=v["css"], jsonld=release_jsonld(r, site))
    # Direct store buttons (content/store_links.json). The first PRIMARY ones are always shown; if 2+ more remain they sit
    # behind a "More" toggle (shown by default without JS). HyperFollow only appears as a fallback for a release that has
    # no direct links yet.
    listen = ""
    stores = r.get("store_links") or []
    if stores:
        PRIMARY = ("Spotify", "Apple Music", "YouTube Music", "Amazon Music")
        extra = [x for x in stores if x["name"] not in PRIMARY]
        if len(extra) < 2 or len(extra) == len(stores): extra = []   # a single extra (or nothing primary) is shown inline
        main_ = [x for x in stores if x not in extra]
        li = lambda s_, cls="": (f'<li{cls}><a class="store" href="{e(s_["url"])}" target="_blank" rel="noopener">'
                                 f'{e(s_["name"])}{EXT}{NT}</a></li>')
        more_btn = (f'<li class="more-li"><button type="button" class="store store-more" aria-expanded="false" aria-controls="stores-{r["slug"]}">'
                    f'More<span class="more-n"> ({len(extra)})</span></button></li>') if extra else ""
        listen = (f'<div class="stores"><p class="stores-label" id="stores-label">Listen on</p>'
                  f'<ul class="store-row" id="stores-{r["slug"]}" aria-labelledby="stores-label"{" data-collapsed" if extra else ""}>'
                  + "".join(li(x) for x in main_) + "".join(li(x, ' class="store-extra"') for x in extra) + more_btn + "</ul></div>")
    elif r.get("listen_url"):
        listen = (f'<a class="btn" href="{e(r["listen_url"])}" target="_blank" rel="noopener" data-gc="event/store/hyperfollow/{r["slug"]}">'
                  f'<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>Pre-save / listen{NT}</a>')
    tracks = []
    def pv_btn(t):
        if not t.get("preview"):
            return '<span class="pv-gap" aria-hidden="true"></span>'
        return (f'<button type="button" class="pv" data-src="{root}{t["preview"]}" data-title="{e(t["title"])}" '
                f'aria-label="Play 30-second preview of {e(t["title"])}">{PLAY_ICON}{PAUSE_ICON}</button>')
    for t in r["tracks"]:
        bar = '<span class="pv-bar" aria-hidden="true"><span></span></span>' if t.get("preview") else ""
        if t["lyrics"] == "lyrics" and r.get("lyrics_file"):
            tracks.append(f'<li class="has-lyrics">{pv_btn(t)}<span class="n">{t["n"]}</span>{bar}<details data-isrc="{e(t["isrc"])}">'
                          f'<summary><span class="tt">{e(t["title"])}</span><span class="ltag" aria-hidden="true">Lyrics</span>'
                          f'<span class="sr-only"> — show lyrics</span></summary>'
                          + (f'<p class="tblurb">{e(t["blurb"])}</p>' if t.get("blurb") else "")
                          + f'<div class="lyrics" aria-live="polite">Loading lyrics…</div>'
                          f'<p class="lcopy">&copy; {r["release_date"][:4]} {LABEL_NAME}. All rights reserved.</p></details></li>')
        else:
            tag = ' <span class="itag">Instrumental</span>' if t["lyrics"] == "instrumental" else ""
            tracks.append(f'<li>{pv_btn(t)}<span class="n">{t["n"]}</span>{bar}<span class="tt">{e(t["title"])}{tag}</span></li>')
    first = next((t for t in r["tracks"] if t.get("preview")), None)
    preview_bar = (f'<div class="pv-main"><button type="button" class="pv-top" data-first="{root}{first["preview"]}" '
                   f'aria-label="Play 30-second preview of {e(first["title"])}">{PLAY_ICON}{PAUSE_ICON}'
                   f'<span class="pv-top-label">Play preview</span></button>'
                   f'<span class="pv-status"><span class="pv-now">{e(first["title"])}</span>'
                   f'<span class="pv-time" aria-hidden="true">0:00 / 0:30</span></span>'
                   f'<span class="pv-note">30s previews</span></div>') if first else ""
    n = len(r["tracks"])
    facts = (f'<li><span>Released</span> <span class="js-upcoming"{hid_up}>Out </span><time datetime="{r["release_date"]}">{e(r["release_date_display"])}</time></li>'
             + (f'<li><span>Genre</span> {genre_link(root, r["genre"])}</li>' if r.get("genre") else "")
             + f'<li>{n} track{"s" if n != 1 else ""}</li>'
             + ('<li class="fact-instr">Instrumental</li>' if r.get("category") == "instrumental" else "")
             + (f'<li><span>Label</span> {e(r["label"])}</li>' if r.get("label") else ""))
    # previous = older release, next = newer release (list is newest first)
    def pager_link(x, rel, label):
        if not x: return '<span class="pager-gap" aria-hidden="true"></span>'
        return (f'<a class="pager-link pager-{rel}" href="{root}release/{x["slug"]}/" rel="{rel}">'
                f'{picture(root, x, "64px", alt="")}<span class="pl-text"><span class="pl-k">{label}</span>'
                f'<span class="pl-t">{e(x["title"])}</span><span class="pl-s">{"Album" if x["type"] == "album" else "Single"} · {short_date(x["release_date"])}</span></span></a>')
    older = releases[i + 1] if i + 1 < len(releases) else None
    newer = releases[i - 1] if i > 0 else None
    # "More": same category first (same type, then the other type), then the other category; newest first within each
    cat = r.get("category", "vocal"); anchor = cat_anchor(r)
    others = [x for x in releases if x["slug"] != r["slug"]]
    rank = lambda x: (x.get("category", "vocal") != cat, x["type"] != r["type"])
    more = sorted(others, key=rank)[:6]   # sorted() is stable, so newest-first order is kept inside each group
    more_label = "songs" if cat == "vocal" else "instrumentals"
    more_html = (f'''
  <section class="section more" aria-labelledby="more-title">
    <div class="section-head"><h2 id="more-title">More {more_label}</h2>
      <a class="count" href="{root}#{anchor}">See all</a></div>
    <ul class="grid grid-singles">{"".join(card(root, x, SINGLE_SIZES, today) for x in more)}</ul>
  </section>''' if more else "")
    bg = f' style="background-image:url(\'{root}{r["cover"]["jpg_small"]}\')"' if r.get("cover") else ""
    lyr = f' data-lyrics="{root}{r["lyrics_file"]}"' if r.get("lyrics_file") else ""
    page = f'''{hd}
<body class="release-page">
{topbar(root, has_about)}
<main id="main">
  <div class="release-bg"{bg} aria-hidden="true"></div>
  <article class="release" data-slug="{r["slug"]}" data-date="{r["release_date"]}"{lyr}>
    <div class="cover-col"><div class="cover">{picture(root, r, "(max-width: 820px) 92vw, 560px", eager=True, big=True)}</div>
      <p class="art-copy">Artwork &copy; {r["release_date"][:4]} {LABEL_NAME}. All rights reserved.</p></div>
    <div class="release-body">
      <a class="back" href="{root}#{anchor}"><span aria-hidden="true">←</span> All {more_label}</a>
      <p class="eyebrow">{kind}<span class="js-upcoming"{hid_up}> · Upcoming</span></p>
      <h1 style="--fit:{word_fit(r["title"]) or 1}">{e(r["title"])}</h1>
      <p class="by">{ARTIST}</p>{f'{chr(10)}      <p class="blurb">{e(r["blurb"])}</p>' if r.get("blurb") else ""}
      <ul class="facts">{facts}</ul>
      {preview_bar}
      <div class="listen">{listen}{buy_html(r.get("download_url"), "Download", "dl-soon", f"event/download/{r['slug']}")}</div>
      <h2 class="tracks-title">Tracklist</h2>
      <ol class="tracks">{"".join(tracks)}</ol>
    </div>
  </article>
  <nav class="pager" aria-label="Previous and next release">
    {pager_link(older, "prev", "Previous release")}
    {pager_link(newer, "next", "Next release")}
  </nav>{more_html}
</main>

{footer(root, v["js"])}'''
    d = ROOT / "release" / r["slug"]; d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(page)

def _counts_line(rs):
    nt = sum(len(r["tracks"]) for r in rs); ns, ni = track_counts(rs)
    parts = [f"{len(rs)} release{'s' if len(rs) != 1 else ''}", f"{nt} track{'s' if nt != 1 else ''}"]
    return parts, ns, ni

def build_genres(releases, site, today, v, has_about):
    groups = genre_groups(releases)
    gdir = ROOT / "genre"
    keep = {genre_slug(g) for g, _ in groups}
    if gdir.exists():   # drop pages for genres that no longer exist
        for d in gdir.iterdir():
            if d.is_dir() and d.name not in keep:
                for f in d.iterdir(): f.unlink()
                d.rmdir()
    # ---- one page per genre
    for g, rs in groups:
        root = "../../"; slug = genre_slug(g); url = f"{site}genre/{slug}/"
        parts, ns, ni = _counts_line(rs)
        mix = " · ".join(x for x in [f"{ns} song{'s' if ns != 1 else ''}" if ns else "", f"{ni} instrumental{'s' if ni != 1 else ''}" if ni else ""] if x)
        desc = (f"{g} music by {ARTIST}: {parts[0]} and {parts[1]} ({mix}), released on {LABEL_NAME}.")
        og = site + f"assets/img/og/genre-{slug}.jpg"
        ld = {"@context": "https://schema.org", "@type": "CollectionPage", "@id": url + "#page", "name": f"{g} — {ARTIST}", "url": url,
              "description": desc, "inLanguage": "en", "isPartOf": {"@type": "WebSite", "name": ARTIST, "url": site},
              "about": {"@type": "Thing", "name": g}, "genre": g,
              "breadcrumb": {"@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": ARTIST, "item": site},
                  {"@type": "ListItem", "position": 2, "name": "Genres", "item": site + "genres/"},
                  {"@type": "ListItem", "position": 3, "name": g, "item": url}]},
              "mainEntity": {"@type": "ItemList", "numberOfItems": len(rs), "itemListElement": [
                  {"@type": "ListItem", "position": k + 1, "url": f"{site}release/{r['slug']}/",
                   "item": {"@type": "MusicAlbum", "name": r["title"], "url": f"{site}release/{r['slug']}/", "datePublished": r["release_date"],
                            "genre": g, "byArtist": {"@type": "MusicGroup", "name": ARTIST}}} for k, r in enumerate(rs)]}}
        hd = head(root, title=f"{g} — {ARTIST}", desc=desc, url=url, og_image=og,
                  og_alt=f"{g}: collage of {ARTIST} cover art", css_v=v["css"], jsonld=ld)
        page = f'''{hd}
<body class="genre-page">
{topbar(root, has_about, current="genres")}
<main id="main">
  <header class="section genre-head">
    <a class="back" href="{root}genres/"><span aria-hidden="true">←</span> All genres</a>
    <p class="eyebrow">Genre</p>
    <h1>{e(g)}</h1>
    <p class="genre-stats">{" · ".join(parts)}<span class="sep" aria-hidden="true"> · </span><span class="mix">{mix}</span></p>
  </header>{cat_sections_html(root, rs, today)}
</main>

{footer(root, v["js"])}'''
        d = gdir / slug; d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page)
    # ---- genres index
    root = "../"; url = site + "genres/"
    tiles = []
    for g, rs in groups:
        parts, ns, ni = _counts_line(rs)
        covers = [r for r in rs if r.get("cover")][:4]
        if len(covers) == 2: covers = [covers[0], covers[1], covers[1], covers[0]]   # checkerboard, always a full 2x2
        elif covers and len(covers) < 4: covers = (covers * 4)[:4]
        mosaic = "".join(f'<img src="{root}{r["cover"]["webp_small"]}" width="400" height="400" alt="" loading="lazy" decoding="async">' for r in covers)
        mix = " · ".join(x for x in [f"{ns} song{'s' if ns != 1 else ''}" if ns else "", f"{ni} instrumental{'s' if ni != 1 else ''}" if ni else ""] if x)
        tiles.append(f'''<li class="gcard"><a class="gcard-link" href="{genre_href(root, g)}">
        <div class="mosaic" aria-hidden="true">{mosaic}</div>
        <div class="ginfo"><h2 class="gname">{e(g).replace("/", "/<wbr>")}</h2><p class="sub">{" · ".join(parts)}</p><p class="sub mix">{mix}</p></div></a></li>''')
    nrel = sum(len(rs) for _, rs in groups); ntr = sum(len(r["tracks"]) for _, rs in groups for r in rs)
    desc = f"Browse {ARTIST} by genre: {', '.join(g for g, _ in groups)} — {nrel} releases and {ntr} tracks."
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "@id": url + "#page", "name": f"Genres — {ARTIST}", "url": url,
          "description": desc, "inLanguage": "en", "isPartOf": {"@type": "WebSite", "name": ARTIST, "url": site},
          "mainEntity": {"@type": "ItemList", "numberOfItems": len(groups), "itemListElement": [
              {"@type": "ListItem", "position": k + 1, "name": g, "url": f"{site}genre/{genre_slug(g)}/"} for k, (g, _) in enumerate(groups)]}}
    hd = head(root, title=f"Genres — {ARTIST}", desc=desc, url=url, og_image=site + "assets/img/og/home.jpg",
              og_alt=f"{ARTIST} wordmark over a collage of cover art", css_v=v["css"], jsonld=ld)
    page = f'''{hd}
<body class="genres-page">
{topbar(root, has_about, current="genres")}
<main id="main">
  <header class="section genre-head">
    <a class="back" href="{root}"><span aria-hidden="true">←</span> Home</a>
    <p class="eyebrow">Browse</p>
    <h1>Genres</h1>
    <p class="genre-stats">{len(groups)} genres · {nrel} releases · {ntr} tracks</p>
  </header>
  <section class="section genres-sec" aria-label="All genres">
    <ul class="ggrid">
      {"".join(tiles)}
    </ul>
  </section>
</main>

{footer(root, v["js"])}'''
    (ROOT / "genres").mkdir(exist_ok=True)
    (ROOT / "genres" / "index.html").write_text(page)
    return groups

LOUNGE_INTRO = "A home for the people who stand with bfo.mantis."
LOUNGE_ITEMS = [   # user-approved wording; no prices, tiers, perks beyond these, or member counts
    "Exclusive music: demos, unreleased tracks, and full downloads",
    "Behind-the-scenes posts, song stories, and early announcements",
    "A community space to talk with other fans and with bfo.mantis",
    "A free email sign-up for news and early access",
]

def build_lounge(site, v, has_about, members_url=None):
    root = "../"; url = site + "lounge/"
    desc = f"Members Lounge (coming soon): {LOUNGE_INTRO} Exclusive music, behind-the-scenes posts, a fan community and a free email sign-up."
    ld = {"@context": "https://schema.org", "@type": "WebPage", "@id": url + "#page", "name": f"Members Lounge — {ARTIST}", "url": url,
          "description": desc, "inLanguage": "en", "isPartOf": {"@type": "WebSite", "name": ARTIST, "url": site},
          "about": music_group(site)}
    hd = head(root, title=f"Members Lounge — {ARTIST}", desc=desc, url=url, og_image=site + "assets/img/og/home.jpg",
              og_alt=f"{ARTIST} wordmark over a collage of cover art", css_v=v["css"], jsonld=ld)
    items = "".join(f'<li>{e(t)}</li>' for t in LOUNGE_ITEMS)
    page = f'''{hd}
<body class="lounge-page">
{topbar(root, has_about, current="lounge")}
<main id="main">
  <section class="section lounge" aria-labelledby="lounge-title">
    <a class="back" href="{root}"><span aria-hidden="true">←</span> Home</a>
    <p class="eyebrow">bfo.mantis</p>
    <div class="lounge-title"><h1 id="lounge-title">Members Lounge</h1><span class="soon-tag">Coming soon</span></div>
    <p class="lounge-intro">{e(LOUNGE_INTRO)}</p>
    <h2 class="lounge-sub">What members will get</h2>
    <ul class="perks">{items}</ul>
    {buy_html(members_url, "Join", "join-soon", "event/join")}
  </section>
</main>

{footer(root, v["js"])}'''
    (ROOT / "lounge").mkdir(exist_ok=True)
    (ROOT / "lounge" / "index.html").write_text(page)

def build_covers_zip(releases):
    """assets/press/bfo-mantis-cover-art.zip: every 800px cover JPG + a notice. Deterministic (fixed timestamps), so an
    unchanged set of covers gives a byte-identical zip and no git churn."""
    import zipfile
    out = ROOT / "assets" / "press"; out.mkdir(parents=True, exist_ok=True)
    z = out / "bfo-mantis-cover-art.zip"
    notice = (f"Cover art for releases by {ARTIST}.\nArtwork (c) {COPY_YEAR} {LABEL_NAME}. All rights reserved.\n"
              f"Provided for press and editorial use in connection with {ARTIST} releases.\n")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zf:   # JPGs don't compress further
        def add(name, data):
            zi = zipfile.ZipInfo(name, date_time=(2026, 7, 4, 0, 0, 0)); zi.external_attr = 0o644 << 16
            zf.writestr(zi, data)
        add("README.txt", notice.encode())
        for r in sorted(releases, key=lambda x: x["release_date"]):
            if r.get("cover"):
                add(f"{r['release_date']}_{r['slug']}.jpg", (ROOT / r["cover"]["jpg"]).read_bytes())
    return "assets/press/" + z.name, z.stat().st_size

def build_press(releases, site, v, has_about, about, tagline, press_contact):
    root = "../"; url = site + "press/"
    zip_path, zip_size = build_covers_zip(releases)
    albums = sum(r["type"] == "album" for r in releases); singles = len(releases) - albums
    ntr = sum(len(r["tracks"]) for r in releases)
    genres = [g for g, _ in genre_groups(releases)]
    first = min(releases, key=lambda r: r["release_date"])
    since = date.fromisoformat(first["release_date"]); since_s = since.strftime("%B ") + str(since.day) + since.strftime(", %Y")
    desc = (f"Press kit for {ARTIST}: bio, catalog facts, release list and downloadable cover art. "
            f"{len(releases)} releases on {LABEL_NAME} since {since_s}.")
    ld = {"@context": "https://schema.org", "@type": "AboutPage", "@id": url + "#page", "name": f"Press kit — {ARTIST}", "url": url,
          "description": desc, "inLanguage": "en", "isPartOf": {"@type": "WebSite", "name": ARTIST, "url": site},
          "about": {**music_group(site), "foundingDate": first["release_date"], "genre": genres,
                    "recordLabel": {"@type": "Organization", "name": LABEL_NAME}}}
    hd = head(root, title=f"Press kit — {ARTIST}", desc=desc, url=url, og_image=site + "assets/img/og/home.jpg",
              og_alt=f"{ARTIST} wordmark over a collage of cover art", css_v=v["css"], jsonld=ld)
    rows = "".join(
        f'<tr><td class="pk-cover">{picture(root, r, "56px", alt="")}</td>'
        f'<th scope="row"><a href="{root}release/{r["slug"]}/">{e(r["title"])}</a></th>'
        f'<td>{"Album" if r["type"] == "album" else "Single"}{f" · {len(r["tracks"])} tracks" if r["type"] == "album" else ""}</td>'
        f'<td><time datetime="{r["release_date"]}">{e(r["release_date_display"])}</time></td>'
        f'<td>{genre_link(root, r["genre"]) if r.get("genre") else ""}</td>'
        f'<td>' + (f'<a class="pk-dl" href="{root}{r["cover"]["jpg"]}" download="{r["slug"]}-cover-800.jpg">JPG 800px<span class="sr-only"> cover art for {e(r["title"])}</span></a>' if r.get("cover") else "") + '</td></tr>'
        for r in releases)
    if press_contact:
        href = press_contact if press_contact.startswith("https://") else f"mailto:{press_contact}"
        contact = f'<p><a class="btn-alt" href="{e(href)}"{" target=\"_blank\" rel=\"noopener\"" if href.startswith("https://") else ""}>{e(press_contact)}</a></p>'
    else:
        contact = '<p class="pk-soon"><span class="soon-tag">Coming soon</span> A press contact will be listed here.</p>'
    bio = f'<div class="about-body">{about}</div>' if about else ""
    page = f'''{hd}
<body class="press-page">
{topbar(root, has_about, current="press")}
<main id="main">
  <section class="section press" aria-labelledby="press-title">
    <a class="back" href="{root}"><span aria-hidden="true">←</span> Home</a>
    <p class="eyebrow">Press kit</p>
    <h1 id="press-title">bfo<span>.</span>mantis</h1>
    {f'<p class="pk-tagline">{e(tagline)}</p>' if tagline else ""}
  </section>

  <section class="section" aria-labelledby="pk-bio">
    <div class="section-head"><h2 id="pk-bio">Bio</h2></div>
    {bio}
  </section>

  <section class="section" aria-labelledby="pk-facts">
    <div class="section-head"><h2 id="pk-facts">Catalog facts</h2></div>
    <dl class="pk-facts">
      <div><dt>Releases</dt><dd>{len(releases)} ({albums} albums, {singles} singles)</dd></div>
      <div><dt>Tracks</dt><dd>{ntr}</dd></div>
      <div><dt>Genres</dt><dd>{", ".join(genre_link(root, g) for g in genres)}</dd></div>
      <div><dt>Active since</dt><dd><time datetime="{first["release_date"]}">{since_s}</time></dd></div>
      <div><dt>Label</dt><dd>{LABEL_NAME}</dd></div>
    </dl>
  </section>

  <section class="section" aria-labelledby="pk-releases">
    <div class="section-head"><h2 id="pk-releases">Releases &amp; cover art</h2>
      <a class="btn-alt pk-zip" href="{root}{zip_path}" download>Download all covers (ZIP, {zip_size / 1e6:.1f} MB)</a></div>
    <div class="pk-table-wrap"><table class="pk-table">
      <thead><tr><th scope="col"><span class="sr-only">Cover</span></th><th scope="col">Title</th><th scope="col">Type</th><th scope="col">Released</th><th scope="col">Genre</th><th scope="col">Cover art</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
    <p class="art-copy">Artwork &copy; {COPY_YEAR} {LABEL_NAME}. All rights reserved.</p>
  </section>

  <section class="section" aria-labelledby="pk-photos">
    <div class="section-head"><h2 id="pk-photos">Press photos</h2></div>
    <p class="pk-soon"><span class="soon-tag">Coming soon</span></p>
  </section>

  <section class="section" aria-labelledby="pk-contact">
    <div class="section-head"><h2 id="pk-contact">Contact</h2></div>
    {contact}
  </section>
</main>

{footer(root, v["js"])}'''
    (ROOT / "press").mkdir(exist_ok=True)
    (ROOT / "press" / "index.html").write_text(page)
    return zip_size

def build_misc(releases, site, v):
    # old URL shim: release.html?r=<slug> -> release/<slug>/
    slugs = json.dumps([r["slug"] for r in releases])
    (ROOT / "release.html").write_text(f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{ARTIST}</title>
<script>(function(){{var s=(new URLSearchParams(location.search).get("r")||"").trim().toLowerCase().replace(/^\/+|\/+$/g,""),k={slugs};location.replace(s&&k.indexOf(s)>-1?"release/"+encodeURIComponent(s)+"/":"./");}})();</script>
<style>body{{background:#0b0b0f;color:#ecebf2;font:16px/1.6 system-ui,sans-serif;padding:40px}}a{{color:#c8ff4d}}</style>
</head>
<body><p>Redirecting… <a href="./">Go to {ARTIST}</a></p></body>
</html>
''')
    # 404: self-contained (works at any URL depth; links are root-absolute on purpose)
    (ROOT / "404.html").write_text(f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<meta name="theme-color" content="#0b0b0f">
<title>Page not found — {ARTIST}</title>{goatcounter_tag()}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<style>
@font-face{{font-family:Syne;font-weight:700 800;font-display:swap;src:url(/assets/fonts/syne-latin.woff2) format("woff2")}}
@font-face{{font-family:Inter;font-weight:400 700;font-display:swap;src:url(/assets/fonts/inter-latin.woff2) format("woff2")}}
*{{box-sizing:border-box}}html,body{{height:100%}}
body{{margin:0;background:#0b0b0f radial-gradient(90% 70% at 20% 100%,rgba(200,255,77,.07),transparent 60%);color:#ecebf2;font:400 16px/1.6 Inter,system-ui,sans-serif;display:flex;flex-direction:column}}
header{{padding:14px clamp(16px,4vw,40px);border-bottom:1px solid #262632}}
.brand{{font:800 1.25rem/1 Syne,system-ui,sans-serif;color:#ecebf2;text-decoration:none}}.brand span,.big span{{color:#c8ff4d}}
main{{flex:1;display:flex;align-items:center;padding:clamp(32px,8vw,96px) clamp(16px,4vw,40px)}}
.wrap{{max-width:1240px;width:100%;margin:0 auto}}
.k{{margin:0 0 8px;text-transform:uppercase;letter-spacing:.2em;font-size:.78rem;color:#c8ff4d;font-weight:600}}
.big{{font:800 clamp(5rem,22vw,14rem)/.85 Syne,system-ui,sans-serif;letter-spacing:-.05em;margin:0}}
h1{{font:700 clamp(1.5rem,3.5vw,2.2rem)/1.15 Syne,system-ui,sans-serif;margin:22px 0 8px;letter-spacing:-.02em}}
p.m{{color:#a3a2b3;margin:0 0 28px;max-width:46ch}}
.row{{display:flex;flex-wrap:wrap;gap:10px}}
.btn{{display:inline-flex;align-items:center;gap:8px;background:#c8ff4d;color:#0b0b0f;font-weight:700;text-decoration:none;padding:13px 22px;border-radius:999px}}
.ghost{{display:inline-flex;align-items:center;border:1px solid #3a3a4a;color:#ecebf2;text-decoration:none;padding:12px 18px;border-radius:999px;font-weight:500}}
.ghost:hover{{border-color:#c8ff4d}}.btn:hover{{box-shadow:0 10px 30px -8px rgba(200,255,77,.5)}}
:focus-visible{{outline:3px solid #c8ff4d;outline-offset:3px;border-radius:8px}}
footer{{padding:22px clamp(16px,4vw,40px);color:#a3a2b3;font-size:.9rem;border-top:1px solid #262632}}
</style>
</head>
<body>
<header><a class="brand" href="/">bfo<span>.</span>mantis</a></header>
<main id="main"><div class="wrap">
  <p class="k">Error 404</p>
  <p class="big" aria-hidden="true">4<span>0</span>4</p>
  <h1>This page doesn’t exist.</h1>
  <p class="m">The link may be old or mistyped. Everything from {ARTIST} is on the home page.</p>
  <div class="row"><a class="btn" href="/">Back to home</a><a class="ghost" href="/#songs">Songs</a><a class="ghost" href="/#instrumentals">Instrumentals</a></div>
</div></main>
<footer>Music, lyrics, artwork and audio previews &copy; {COPY_YEAR} {LABEL_NAME}. All rights reserved.</footer>
</body>
</html>
''')
    urls = ([site] + [f"{site}release/{r['slug']}/" for r in releases] + [site + "genres/", site + "lounge/", site + "press/"]
            + [f"{site}genre/{genre_slug(g)}/" for g, _ in genre_groups(releases)])
    (ROOT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
                                      "".join(f"  <url><loc>{e(u)}</loc></url>\n" for u in urls) + "</urlset>\n")
    # Lyrics live only in assets/data/lyrics/*.json (fetched on demand by release pages); keep them out of search.
    # GitHub Pages can't send X-Robots-Tag headers, so robots.txt is the lever.
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /assets/data/lyrics/\n\nSitemap: {site}sitemap.xml\n")
    (ROOT / "site.webmanifest").write_text(json.dumps({
        "name": ARTIST, "short_name": ARTIST, "start_url": "./", "display": "standalone",
        "background_color": "#0b0b0f", "theme_color": "#0b0b0f",
        "icons": [{"src": "assets/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "assets/img/icon-512.png", "sizes": "512x512", "type": "image/png"}]}, indent=1) + "\n")

def main(site_url="https://bfo-mantis.github.io/", images=True):
    site = site_url.rstrip("/") + "/"
    data = json.loads((ROOT / "assets" / "data" / "releases.json").read_text())
    releases = data["releases"]
    global GOATCOUNTER
    GOATCOUNTER = data.get("goatcounter_code")
    today = date.today()
    about = about_html(); has_about = bool(about)
    albums = sum(r["type"] == "album" for r in releases); singles = len(releases) - albums
    if images:
        ns, ni = track_counts(releases)
        build_images(releases, f"{ns} songs · {ni} instrumentals")
    v = {"css": asset_hash("css/style.css"), "js": asset_hash("js/app.js")}
    build_home(releases, site, today, v, has_about, about, data.get("donate_url"))
    rel = ROOT / "release"
    keep = {r["slug"] for r in releases}
    if rel.exists():
        for d in rel.iterdir():
            if d.is_dir() and d.name not in keep:
                for f in d.iterdir(): f.unlink()
                d.rmdir()
    for i in range(len(releases)):
        build_release(releases, i, site, today, v, has_about)
    groups = build_genres(releases, site, today, v, has_about)
    build_lounge(site, v, has_about, data.get("members_url"))
    bl = ROOT / "content" / "blurbs.json"
    tagline = (json.loads(bl.read_text()).get("artist") or {}).get("tagline") if bl.exists() else None
    zsize = build_press(releases, site, v, has_about, about, tagline, data.get("press_contact"))
    build_misc(releases, site, v)
    print("genres:", ", ".join(f"{g} ({len(rs)} releases, {sum(len(r['tracks']) for r in rs)} tracks)" for g, rs in groups))
    print(f"pages: index + {len(releases)} release pages + genres index + {len(groups)} genre pages + lounge + press (covers zip {zsize / 1e6:.1f} MB) + 404 + release.html shim | sitemap urls: {len(releases) + 4 + len(groups)} | about section: {'shown' if has_about else 'hidden (content/about.html empty)'}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-url", default="https://bfo-mantis.github.io/")
    ap.add_argument("--skip-images", action="store_true")
    a = ap.parse_args()
    main(a.site_url, not a.skip_images)
