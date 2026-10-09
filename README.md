# bfo.mantis — static site

Plain HTML/CSS/vanilla JS. No build step, all paths relative.

```
index.html            home: hero, albums grid, singles grid, bio placeholder
release.html?r=<slug> release detail (cover, date, genre, tracklist, listen button)
css/style.css         styles (fonts: Syne + Inter via Google Fonts)
js/app.js             renders pages from assets/data/releases.js
assets/data/          releases.js (loaded by pages) + releases.json (same data) — GENERATED
assets/covers/        <slug>-800 / -400 .jpg + .webp — GENERATED
tools/build_data.py   regenerates data + covers from the DistroKid catalog
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

## Things to replace
- **Bio**: the dashed "PLACEHOLDER" block in `index.html` (`#about`).

## Deploy
**GitHub Pages**: push this folder to a repo (root of the repo), Settings → Pages → Deploy from branch → `main` / root.
`.nojekyll` is included. Works from a project sub-path (`user.github.io/repo/`) because all paths are relative.

**Netlify**: drag-and-drop this folder at app.netlify.com/drop, or connect the repo; `netlify.toml` publishes `.` with no build command.

`screenshots/` and `tools/.cache/` are git-ignored.
