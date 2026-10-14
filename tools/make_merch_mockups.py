"""Flat product mockups for the Freeborn merch collection -> assets/merch/<id>-1200.(jpg|webp) + -600."""
from PIL import Image, ImageDraw, ImageFilter
from pathlib import Path
A = Path("/workspace/freeborn/merch"); COVER = Path("/workspace/freeborn/freeborn-bfo-mantis-3000.png")
OUT = Path(__file__).resolve().parent.parent / "assets" / "merch"; OUT.mkdir(parents=True, exist_ok=True)
S = 1200; BG = (24, 24, 31)
def art(n): return Image.open(A / n).convert("RGBA")
def fit(im, w, h):
    im = im.copy(); im.thumbnail((w, h), Image.LANCZOS); return im
def canvas():
    c = Image.new("RGB", (S, S), BG); g = Image.new("L", (S, S), 0); d = ImageDraw.Draw(g)
    d.ellipse((150, 120, 1050, 1020), fill=60); g = g.filter(ImageFilter.GaussianBlur(160))
    c.paste((48, 48, 60), (0, 0), g); return c
def shadow(c, mask, off=(0, 22), blur=30, a=150):
    sh = Image.new("L", (S, S), 0); sh.paste(mask.point(lambda p: a if p else 0), off, mask)
    c.paste((0, 0, 0), (0, 0), sh.filter(ImageFilter.GaussianBlur(blur)))
def garment(hood=False):
    m = Image.new("L", (S, S), 0); d = ImageDraw.Draw(m)
    if hood:
        d.polygon([(330,250),(470,200),(730,200),(870,250),(1040,420),(1110,980),(1000,1000),(930,560),(930,1080),(270,1080),(270,560),(200,1000),(90,980),(160,420)], fill=255)
        d.ellipse((440,110,760,330), fill=255)
    else:
        d.polygon([(380,190),(500,160),(700,160),(820,190),(1080,330),(990,520),(900,470),(900,1060),(300,1060),(300,470),(210,520),(120,330)], fill=255)
    return m.filter(ImageFilter.GaussianBlur(1.2))
def shirt(color, prints, hood=False):
    c = canvas(); m = garment(hood); shadow(c, m)
    c.paste(color, (0, 0), m); d = ImageDraw.Draw(c)
    dk = tuple(max(0, int(x*0.8)) for x in color)
    if hood:
        d.ellipse((500,170,700,330), fill=dk); d.rectangle((420,850,780,960), outline=dk, width=6)
        d.line((560,320,555,470), fill=dk, width=6); d.line((640,320,645,470), fill=dk, width=6)
    else:
        d.arc((500,110,700,250), 0, 180, fill=dk, width=14)
    for im, cx, top in prints:
        c.paste(im, (cx - im.width // 2, top), im)
    return c
def save(c, id):
    c = c.convert("RGB")
    for w in (1200, 600):
        x = c if w == S else c.resize((w, w), Image.LANCZOS)
        x.save(OUT / f"{id}-{w}.jpg", quality=84, optimize=True, progressive=True)
        x.save(OUT / f"{id}-{w}.webp", quality=80, method=6)
    print(id)
BLACK, CREAM, RED = (22, 21, 24), (238, 231, 213), (182, 34, 30)
# 1 black tee, crown-figure (white 1c)
save(shirt(BLACK, [(fit(art("freeborn-crown-figure-white-1color-4200x4800.png"), 380, 440), 600, 330)]), "freeborn-tee-crown-figure")
# 2 cream tee, wordmark + crowd strip
save(shirt(CREAM, [(fit(art("freeborn-wordmark-black-6367x1006.png"), 470, 90), 600, 380),
                   (fit(art("freeborn-crowd-strip-6000x1031.png"), 470, 110), 600, 500)]), "freeborn-tee-wordmark")
# 3 black hoodie, red crown + cream wordmark
save(shirt((44, 44, 50), [(fit(art("freeborn-crown-white-1color-4480x3232.png"), 300, 220), 600, 460),
                   (fit(art("freeborn-wordmark-cream-6367x1006.png"), 380, 70), 600, 700)], hood=True), "freeborn-hoodie")
# 4 poster 18x24
c = canvas(); p = fit(Image.open(A / "freeborn-poster-18x24-5400x7200.png").convert("RGB"), 690, 920)
x, y = (S - p.width)//2, (S - p.height)//2 - 10
m = Image.new("L", (S, S), 0); ImageDraw.Draw(m).rectangle((x-12, y-12, x+p.width+12, y+p.height+12), fill=255); shadow(c, m, (14, 26), 26, 170)
ImageDraw.Draw(c).rectangle((x-12, y-12, x+p.width+12, y+p.height+12), fill=(250, 248, 242)); c.paste(p, (x, y)); save(c, "freeborn-poster")
# 5 sticker: die-cut crown on white border
c = canvas(); cr = fit(art("freeborn-crown-red-4480x3232.png"), 640, 480); a = cr.split()[3]
pad = Image.new("L", (cr.width+80, cr.height+80), 0); pad.paste(a, (40, 40)); border = pad.filter(ImageFilter.MaxFilter(41)).filter(ImageFilter.GaussianBlur(2))
bx, by = (S - pad.width)//2, (S - pad.height)//2
full = Image.new("L", (S, S), 0); full.paste(border, (bx, by)); shadow(c, full, (0, 16), 20, 160)
c.paste((248, 246, 240), (0, 0), full); c.paste(cr, (bx+40, by+40), cr); save(c, "freeborn-sticker")
# 6 tote, natural canvas, figure
c = canvas(); d = ImageDraw.Draw(c); m = Image.new("L", (S, S), 0); md = ImageDraw.Draw(m)
md.rectangle((300, 380, 900, 1080), fill=255); shadow(c, m)
d.arc((430, 150, 770, 560), 180, 360, fill=(200, 190, 165), width=34); c.paste((226, 216, 190), (0, 0), m)
c.paste((0,0,0), (0,0), Image.new("L",(S,S),0))
f = fit(art("freeborn-figure-1424x4016.png"), 220, 470); c.paste(f, (600 - f.width//2, 430), f)
w = fit(art("freeborn-wordmark-black-6367x1006.png"), 420, 70); c.paste(w, (600 - w.width//2, 940), w); save(c, "freeborn-tote")
# 7 mug, black, cover
c = canvas(); d = ImageDraw.Draw(c); m = Image.new("L", (S, S), 0); md = ImageDraw.Draw(m)
md.rounded_rectangle((270, 330, 830, 960), 26, fill=255); md.ellipse((760, 470, 1010, 820), fill=255); shadow(c, m)
d.ellipse((760, 470, 1010, 820), fill=BLACK); d.ellipse((815, 545, 945, 745), fill=BG)
d.rounded_rectangle((270, 330, 830, 960), 26, fill=BLACK)
cv = fit(Image.open(COVER).convert("RGB"), 400, 400); c.paste(cv, (350, 445)); save(c, "freeborn-mug")
