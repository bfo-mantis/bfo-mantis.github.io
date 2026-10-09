#!/usr/bin/env python3
"""Generate the static HTML pages, share images, icons, sitemap and robots.txt from
assets/data/releases.json (which tools/build_data.py writes from the catalog).

Run automatically at the end of tools/build_data.py, or on its own:
    python3 tools/build_pages.py [--site-url https://bfo-mantis.github.io/]

Outputs (all GENERATED, all links relative so the site also works from a sub-path):
  index.html                     home (pre-rendered: hero, albums, singles, optional About)
  release/<slug>/index.html      one static page per release (title, meta, Open Graph, JSON-LD)
  release.html                   tiny redirect so old release.html?r=<slug> links keep working
  404.html                       self-contained "not found" page
  sitemap.xml, robots.txt, site.webmanifest, favicon.svg/.ico, apple-touch-icon.png, assets/img/icon-*.png
  assets/img/hero-*.{webp,jpg}   pre-blurred cover collage for the hero (one image instead of 24)
  assets/img/og/*.jpg            1200x630 share images (home + one per release)
Lyrics are never written into HTML, JSON-LD or the sitemap; release pages fetch them on demand.
"""
import argparse, hashlib, html, json, math, re
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

def card(root, r, sizes, today, eager=False):
    n = len(r["tracks"])
    sub = (f"{n} track{'s' if n != 1 else ''} · " if r["type"] == "album" else "") + short_date(r["release_date"]) + (f" · {e(r['genre'])}" if r.get("genre") else "")
    up, hid_up, _ = updown(r, today)
    badge = f'<span class="badge js-upcoming"{hid_up}>Out {short_date(r["release_date"]).rsplit(",", 1)[0]}</span>'
    return (f'<li class="card" data-date="{r["release_date"]}"><a class="card-link" href="{root}release/{r["slug"]}/">'
            f'<div class="art">{picture(root, r, sizes, eager, alt="")}{badge}</div>'
            f'<div class="info"><h3 class="title">{e(r["title"])}</h3><p class="sub">{sub}</p></div></a></li>')

ALBUM_SIZES = "(max-width: 520px) 46vw, (max-width: 1240px) 24vw, 280px"
SINGLE_SIZES = "(max-width: 520px) 46vw, (max-width: 1240px) 16vw, 190px"

def head(root, *, title, desc, url, og_image, og_alt, og_type="website", extra="", noindex=False, css_v="", jsonld=None):
    j = f'\n<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False, separators=(",", ":"))}</script>' if jsonld else ""
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
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
<link rel="stylesheet" href="{root}css/style.css?v={css_v}">{j}
</head>'''

def topbar(root, has_about, home=False):
    p = "" if home else root
    about = f'<a href="{p}#about">About</a>' if has_about else ""
    return f'''<a class="skip" href="#main">Skip to content</a>
<header class="topbar" id="top">
  <a class="brand" href="{root or './'}" aria-label="{ARTIST} home">bfo<span>.</span>mantis</a>
  <nav aria-label="Primary">
    <a href="{p}#albums">Albums</a>
    <a href="{p}#singles">Singles</a>
    {about}
  </nav>
</header>'''

def footer(root, js_v):
    year = date.today().year
    return f'''<footer class="footer">
  <p>&copy; {COPY_YEAR} {LABEL_NAME}. All rights reserved.</p>
  <a class="footer-top" href="#top">Back to top <span aria-hidden="true">↑</span></a>
</footer>
<a class="to-top" href="#top" aria-label="Back to top"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5l-7 7m7-7l7 7M12 5v14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></a>
<script src="{root}js/app.js?v={js_v}" defer></script>
</body>
</html>
'''

NT = '<span class="sr-only"> (opens in a new tab)</span>'
EXT = '<svg class="ext" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'

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
    if r.get("cover"): d["image"] = site + r["cover"]["jpg"]
    if r.get("label"): d["recordLabel"] = {"@type": "Organization", "name": r["label"]}
    d["copyrightHolder"] = {"@type": "Organization", "name": LABEL_NAME}
    d["copyrightYear"] = int(r["release_date"][:4])
    same = [s["url"] for s in r.get("store_links") or []]
    if same: d["sameAs"] = same
    return d

def describe(r):
    n = len(r["tracks"])
    kind = f"a {n}-track {r['genre'] + ' ' if r.get('genre') else ''}album" if r["type"] == "album" else f"a {r['genre'] + ' ' if r.get('genre') else ''}single"
    s = f"{r['title']}, {kind} by {ARTIST}, released {r['release_date_display']}" + (f" on {r['label']}" if r.get("label") else "") + "."
    stores = [x["name"] for x in r.get("store_links") or []]
    if stores:
        s += " Listen on " + ", ".join(stores[:3]) + (" and more." if len(stores) > 3 else ".")
    elif r.get("listen_url"):
        s += " Listen now."
    return s

# ---------------------------------------------------------------- pages
def build_home(releases, site, today, v, has_about, about):
    root = ""
    albums = [r for r in releases if r["type"] == "album"]
    singles = [r for r in releases if r["type"] == "single"]
    ntr = sum(len(r["tracks"]) for r in releases)
    genres = []
    for r in releases:
        if r.get("genre") and r["genre"] not in genres: genres.append(r["genre"])
    desc = (f"Albums and singles by {ARTIST}: {len(albums)} albums and {len(singles)} singles"
            f" ({', '.join(genres[:5])}{' and more' if len(genres) > 5 else ''}), released on bfo.mantis Records.")
    latest = releases[0]
    up, hid_up, hid_rel = updown(latest, today)
    ld = {"@context": "https://schema.org", **music_group(site),
          "album": [{"@type": "MusicAlbum", "name": r["title"], "url": f"{site}release/{r['slug']}/", "datePublished": r["release_date"]} for r in releases]}
    hd = head(root, title=f"{ARTIST} — Albums & Singles", desc=desc, url=site, og_image=site + "assets/img/og/home.jpg",
              og_alt=f"{ARTIST} wordmark over a collage of cover art", og_type="music.musician" if False else "website",
              css_v=v["css"], jsonld=ld,
              extra=f'\n<link rel="preload" as="image" href="assets/img/hero-1600.webp" media="(min-width: 601px)" fetchpriority="high">'
                    f'\n<link rel="preload" as="image" href="assets/img/hero-800.webp" media="(max-width: 600px)" fetchpriority="high">')
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
      <p class="hero-meta"><span>{len(albums)} albums · {len(singles)} singles · {ntr} tracks</span>
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

  <section id="albums" class="section" aria-labelledby="albums-title">
    <div class="section-head">
      <h2 id="albums-title">Albums</h2>
      <p class="count">{len(albums)} albums</p>
    </div>
    <ul class="grid grid-albums">
      {"".join(card(root, r, ALBUM_SIZES, today, i < 4) for i, r in enumerate(albums))}
    </ul>
  </section>

  <section id="singles" class="section" aria-labelledby="singles-title">
    <div class="section-head">
      <h2 id="singles-title">Singles</h2>
      <p class="count">{len(singles)} singles</p>
    </div>
    <ul class="grid grid-singles">
      {"".join(card(root, r, SINGLE_SIZES, today) for r in singles)}
    </ul>
  </section>{about_sec}
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
    listen = ""
    if r.get("listen_url"):
        if r["listen_source"] == "hyperfollow":
            label = f'<span class="js-released"{hid_rel}>Listen everywhere</span><span class="js-upcoming"{hid_up}>Pre-save / listen</span>'
        else:
            label = "Listen"
        listen = (f'<a class="btn" href="{e(r["listen_url"])}" target="_blank" rel="noopener">'
                  f'<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>{label}{NT}</a>')
    stores = [s for s in r.get("store_links") or [] if s["url"] != r.get("listen_url")]
    if stores:
        listen += ('<div class="stores"><p class="stores-label" id="stores-label">Or open in</p><ul class="store-row" aria-labelledby="stores-label">' +
                   "".join(f'<li><a class="store" href="{e(s["url"])}" target="_blank" rel="noopener">{e(s["name"])}{EXT}{NT}</a></li>' for s in stores) +
                   "</ul></div>")
    tracks = []
    for t in r["tracks"]:
        if t["lyrics"] == "lyrics" and r.get("lyrics_file"):
            tracks.append(f'<li class="has-lyrics"><span class="n">{t["n"]}</span><details data-isrc="{e(t["isrc"])}">'
                          f'<summary><span class="tt">{e(t["title"])}</span><span class="ltag" aria-hidden="true">Lyrics</span>'
                          f'<span class="sr-only"> — show lyrics</span></summary>'
                          f'<div class="lyrics" aria-live="polite">Loading lyrics…</div>'
                          f'<p class="lcopy">&copy; {r["release_date"][:4]} {LABEL_NAME}. All rights reserved.</p></details></li>')
        else:
            tag = ' <span class="itag">Instrumental</span>' if t["lyrics"] == "instrumental" else ""
            tracks.append(f'<li><span class="n">{t["n"]}</span><span class="tt">{e(t["title"])}{tag}</span></li>')
    n = len(r["tracks"])
    facts = (f'<li><span>Released</span> <span class="js-upcoming"{hid_up}>Out </span><time datetime="{r["release_date"]}">{e(r["release_date_display"])}</time></li>'
             + (f'<li><span>Genre</span> {e(r["genre"])}</li>' if r.get("genre") else "")
             + f'<li>{n} track{"s" if n != 1 else ""}</li>'
             + (f'<li><span>Label</span> {e(r["label"])}</li>' if r.get("label") else ""))
    # previous = older release, next = newer release (list is newest first)
    def pager_link(x, rel, label):
        if not x: return '<span class="pager-gap" aria-hidden="true"></span>'
        return (f'<a class="pager-link pager-{rel}" href="{root}release/{x["slug"]}/" rel="{rel}">'
                f'{picture(root, x, "64px", alt="")}<span class="pl-text"><span class="pl-k">{label}</span>'
                f'<span class="pl-t">{e(x["title"])}</span><span class="pl-s">{"Album" if x["type"] == "album" else "Single"} · {short_date(x["release_date"])}</span></span></a>')
    older = releases[i + 1] if i + 1 < len(releases) else None
    newer = releases[i - 1] if i > 0 else None
    more = [x for x in releases if x["slug"] != r["slug"] and x["type"] == r["type"]][:6]
    more_html = (f'''
  <section class="section more" aria-labelledby="more-title">
    <div class="section-head"><h2 id="more-title">More {"albums" if r["type"] == "album" else "singles"}</h2>
      <a class="count" href="{root}#{"albums" if r["type"] == "album" else "singles"}">See all</a></div>
    <ul class="grid grid-singles">{"".join(card(root, x, SINGLE_SIZES, today) for x in more)}</ul>
  </section>''' if more else "")
    bg = f' style="background-image:url(\'{root}{r["cover"]["jpg_small"]}\')"' if r.get("cover") else ""
    lyr = f' data-lyrics="{root}{r["lyrics_file"]}"' if r.get("lyrics_file") else ""
    page = f'''{hd}
<body class="release-page">
{topbar(root, has_about)}
<main id="main">
  <div class="release-bg"{bg} aria-hidden="true"></div>
  <article class="release" data-date="{r["release_date"]}"{lyr}>
    <div class="cover-col"><div class="cover">{picture(root, r, "(max-width: 820px) 92vw, 560px", eager=True, big=True)}</div></div>
    <div class="release-body">
      <a class="back" href="{root}#{"albums" if r["type"] == "album" else "singles"}"><span aria-hidden="true">←</span> All {"albums" if r["type"] == "album" else "singles"}</a>
      <p class="eyebrow">{kind}<span class="js-upcoming"{hid_up}> · Upcoming</span></p>
      <h1 style="--fit:{word_fit(r["title"]) or 1}">{e(r["title"])}</h1>
      <p class="by">{ARTIST}</p>
      <ul class="facts">{facts}</ul>
      <div class="listen">{listen}</div>
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
<script>(function(){{var s=new URLSearchParams(location.search).get("r"),k={slugs};location.replace(s&&k.indexOf(s)>-1?"release/"+encodeURIComponent(s)+"/":"./");}})();</script>
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
<title>Page not found — {ARTIST}</title>
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
  <div class="row"><a class="btn" href="/">Back to home</a><a class="ghost" href="/#albums">Albums</a><a class="ghost" href="/#singles">Singles</a></div>
</div></main>
<footer>&copy; {COPY_YEAR} {LABEL_NAME}. All rights reserved.</footer>
</body>
</html>
''')
    urls = [site] + [f"{site}release/{r['slug']}/" for r in releases]
    (ROOT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
                                      "".join(f"  <url><loc>{e(u)}</loc></url>\n" for u in urls) + "</urlset>\n")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {site}sitemap.xml\n")
    (ROOT / "site.webmanifest").write_text(json.dumps({
        "name": ARTIST, "short_name": ARTIST, "start_url": "./", "display": "standalone",
        "background_color": "#0b0b0f", "theme_color": "#0b0b0f",
        "icons": [{"src": "assets/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "assets/img/icon-512.png", "sizes": "512x512", "type": "image/png"}]}, indent=1) + "\n")

def main(site_url="https://bfo-mantis.github.io/", images=True):
    site = site_url.rstrip("/") + "/"
    data = json.loads((ROOT / "assets" / "data" / "releases.json").read_text())
    releases = data["releases"]
    today = date.today()
    about = about_html(); has_about = bool(about)
    albums = sum(r["type"] == "album" for r in releases); singles = len(releases) - albums
    if images:
        build_images(releases, f"{albums} albums · {singles} singles")
    v = {"css": asset_hash("css/style.css"), "js": asset_hash("js/app.js")}
    build_home(releases, site, today, v, has_about, about)
    rel = ROOT / "release"
    keep = {r["slug"] for r in releases}
    if rel.exists():
        for d in rel.iterdir():
            if d.is_dir() and d.name not in keep:
                for f in d.iterdir(): f.unlink()
                d.rmdir()
    for i in range(len(releases)):
        build_release(releases, i, site, today, v, has_about)
    build_misc(releases, site, v)
    print(f"pages: index + {len(releases)} release pages + 404 + release.html shim | sitemap urls: {len(releases) + 1} | about section: {'shown' if has_about else 'hidden (content/about.html empty)'}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-url", default="https://bfo-mantis.github.io/")
    ap.add_argument("--skip-images", action="store_true")
    a = ap.parse_args()
    main(a.site_url, not a.skip_images)
