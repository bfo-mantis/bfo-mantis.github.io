# bfo.mantis — static site

Plain HTML/CSS/vanilla JS, all paths relative. Pages are **pre-rendered** by a small Python build
(no framework, no npm), so they load fast, work without JavaScript and give link previews/search engines real content.

```
index.html                    home: hero, albums, singles (+ About once content/about.html has text)   — GENERATED
release/<slug>/index.html     one page per release: cover, facts, listen + store buttons, tracklist,
                              lyrics toggles, previous/next release, Open Graph + JSON-LD                — GENERATED
release.html                  redirect so old release.html?r=<slug> links keep working                  — GENERATED
404.html                      self-contained not-found page                                             — GENERATED
sitemap.xml, robots.txt, site.webmanifest, favicon.*, apple-touch-icon.png                              — GENERATED
css/style.css                 all styles (self-hosted Inter + Syne, font-display: swap)
js/app.js                     small enhancements only: lyrics loading, compact header, back-to-top,
                              upcoming/released labels refreshed against today's date
assets/data/                  releases.json/.js + lyrics/<slug>.json                                    — GENERATED
assets/covers/                <slug>-800 / -400 .jpg + .webp                                            — GENERATED
assets/img/                   hero collage, share images (og/), app icons                               — GENERATED
assets/fonts/                 Inter + Syne woff2 (SIL OFL, licences included)
content/about.html            artist bio (empty placeholder = About section hidden)
content/lyrics_edits.json     line-level lyric cleanup/redactions, applied at build time
content/lyrics_overrides/     <ISRC>.txt artist-supplied lyrics that replace the DistroKid text
tools/build_data.py           single source: catalog → data, covers, lyrics → then runs build_pages.py
tools/build_pages.py          data → HTML pages, share images, icons, sitemap, robots.txt
tools/fonts/                  TTFs used only to draw the share images
```

## Preview locally
```
python3 -m http.server 8000      # then open http://localhost:8000/
```

## Regenerate data (e.g. when HyperFollow / store links arrive)
```
pip install pillow
python3 tools/build_data.py --catalog /workspace/bfo_mantis_catalog.json \
    [--links /workspace/hyperfollow_links.json] [--skip-covers] [--force-covers]
```
- Only releases whose artist list contains `bfo.mantis` are included (LOVELORN / Wetline is excluded).
- Listen button: `hyperfollow_url` → first store link → DistroKid release page *only if public*
  → otherwise the button is hidden. `distrokid.com/dashboard/...` URLs require login, so they are never used.
- Release pages show the primary button (HyperFollow) plus one labeled button per store in `store_links`
  (only stores actually present; `http://amazon` links are upgraded to https). All open in a new tab with `rel="noopener"`.
- Lyrics: `--lyrics` (default /workspace/bfo_mantis_lyrics.json, keyed by ISRC) and `--lyrics-status`
  (default /workspace/lyrics_status.json). Writes one `assets/data/lyrics/<slug>.json` per release with lyrics;
  release pages fetch it only when a track is expanded. Instrumentals get an "Instrumental" tag.
- `--links` takes a JSON list of `{ "title", "hyperfollow_url", "store_links" }` and overrides the catalog by title.

Pages are rebuilt on every run of `build_data.py` (use `--no-pages` to skip, `--site-url` to change the absolute URL used
for canonical links, Open Graph and the sitemap; default `https://bfo-mantis.github.io/`). To rebuild only the HTML:
`python3 tools/build_pages.py [--skip-images]`. Don't hand-edit generated files; edit the build scripts, `css/`, `js/` or `content/`.

## Things to replace
- **Bio**: write it in `content/about.html` and rebuild; the About section and nav link appear automatically.

## Deploy
**GitHub Pages**: push this folder to a repo (root of the repo), Settings → Pages → Deploy from branch → `main` / root.
`.nojekyll` is included. Works from a project sub-path (`user.github.io/repo/`) because all paths are relative.

**Netlify**: drag-and-drop this folder at app.netlify.com/drop, or connect the repo; `netlify.toml` publishes `.` with no build command.

`screenshots/` and `tools/.cache/` are git-ignored.
