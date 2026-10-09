#!/usr/bin/env python3
"""Cut 30-second MP3 previews from the original masters (which never enter the repo).

    python3 tools/make_previews.py [--audio-index /workspace/bfo_mantis_audio/index.json] [--force] [--only ISRC ...]

For each track on the site (matched by ISRC via assets/data/releases.json):
  * start point: content/preview_starts.json override (seconds, keyed by ISRC) if present; otherwise the
    loudest sustained 30 s window (highest mean RMS energy) that starts after the first 15 % and ends before
    the last 10 % of the track. Tracks shorter than 45 s use the first 30 s (or the whole track).
  * 1 s fade-in, 2 s fade-out, two-pass EBU R128 loudness normalisation to -14 LUFS (true peak -1 dBTP),
    44.1 kHz stereo MP3 at 128 kbps (CBR), ID3 tags stripped except title/artist/copyright.
  * output: assets/audio/previews/<release-slug>/<NN>.mp3 (ASCII-only paths).
The choices are written to content/preview_starts.chosen.json (start, length, method) so you can copy a value
into preview_starts.json and adjust it. Unchanged tracks are skipped unless --force.
Requires ffmpeg/ffprobe on PATH. No Python packages needed.
"""
import argparse, array, json, math, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "audio" / "previews"
OVERRIDES = ROOT / "content" / "preview_starts.json"
CHOSEN = ROOT / "content" / "preview_starts.chosen.json"
CLIP, FADE_IN, FADE_OUT, SR_ANALYSIS, BLOCK = 30.0, 1.0, 2.0, 8000, 0.5
LABEL = "bfo.mantis Records"

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=False, check=True)

def duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path])
    return float(r.stdout.decode().strip())

def loudest_window(path, dur):
    """Mean-square energy per 0.5 s block from an 8 kHz mono decode, then the best 30 s window."""
    pcm = run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR_ANALYSIS), "-f", "s16le", "-"]).stdout
    a = array.array("h"); a.frombytes(pcm[: len(pcm) // 2 * 2])
    if sys.byteorder == "big": a.byteswap()
    n = int(SR_ANALYSIS * BLOCK)
    blocks = [sum(x * x for x in a[i:i + n]) / max(1, len(a[i:i + n])) for i in range(0, len(a), n)]
    win = int(CLIP / BLOCK)
    lo = math.ceil(dur * 0.15 / BLOCK)
    hi = math.floor((dur * 0.90 - CLIP) / BLOCK)          # window must end before the last 10 %
    if hi < lo:                                            # track too short for the margins: centre it
        return max(0.0, round((dur - CLIP) / 2 / BLOCK) * BLOCK), "centred (short track)"
    s = sum(blocks[lo:lo + win]); best, best_i = s, lo
    for i in range(lo + 1, hi + 1):
        s += (blocks[i + win - 1] if i + win - 1 < len(blocks) else 0) - blocks[i - 1]
        if s > best: best, best_i = s, i
    return best_i * BLOCK, "max-energy window"

def make(job, overrides, prev, force):
    isrc, src, slug, n, title = job
    out = OUT / slug / f"{n:02d}.mp3"
    dur = duration(src)
    if isrc in overrides:
        start, method = float(overrides[isrc]), "override"
        length = min(CLIP, max(1.0, dur - start))
    elif dur < 45:
        start, method, length = 0.0, "first 30 s (track < 45 s)", min(CLIP, dur)
    else:
        start, method = loudest_window(src, dur); length = CLIP
    rec = {"slug": slug, "track": n, "title": title, "start": round(start, 2), "length": round(length, 2),
           "track_length": round(dur, 2), "method": method, "file": str(out.relative_to(ROOT)),
           "src_size": os.path.getsize(src)}
    p = prev.get(isrc) or {}
    if not force and out.exists() and all(p.get(k) == rec[k] for k in ("start", "length", "src_size", "file")):
        return isrc, rec, "skipped"
    out.parent.mkdir(parents=True, exist_ok=True)
    trim = ["-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", src]
    meas = run(["ffmpeg", "-hide_banner", "-nostats", *trim, "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"]).stderr.decode()
    m = json.loads(meas[meas.rindex("{"): meas.rindex("}") + 1])
    fo = max(0.0, length - FADE_OUT)
    af = (f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
          f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,"
          f"aresample=44100,afade=t=in:st=0:d={FADE_IN},afade=t=out:st={fo:.3f}:d={min(FADE_OUT, length)}")
    tmp = out.with_suffix(".tmp.mp3")
    run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *trim, "-af", af, "-ac", "2", "-ar", "44100",
         "-c:a", "libmp3lame", "-b:a", "128k", "-map_metadata", "-1", "-id3v2_version", "3",
         "-metadata", f"title={title} (preview)", "-metadata", "artist=bfo.mantis",
         "-metadata", f"copyright=(C) 2026 {LABEL}. All rights reserved.", str(tmp)])
    tmp.replace(out)
    return isrc, rec, "made"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-index", default="/workspace/bfo_mantis_audio/index.json")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()
    index = json.loads(Path(a.audio_index).read_text(encoding="utf-8"))
    rel = json.loads((ROOT / "assets" / "data" / "releases.json").read_text())["releases"]
    overrides = {k: v for k, v in (json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}).items() if not k.startswith("_")}
    prev = json.loads(CHOSEN.read_text()) if CHOSEN.exists() else {}
    jobs, missing = [], []
    for r in rel:
        for t in r["tracks"]:
            if a.only and t["isrc"] not in a.only: continue
            e = index.get(t["isrc"])
            if not e or not Path(e["path"]).exists():
                missing.append(t["isrc"]); continue
            jobs.append((t["isrc"], e["path"], r["slug"], t["n"], t["title"]))
    results, failed = dict(prev), []
    with ThreadPoolExecutor(a.jobs) as ex:
        futs = {ex.submit(make, j, overrides, prev, a.force): j for j in jobs}
        for f in futs:
            j = futs[f]
            try:
                isrc, rec, status = f.result(); results[isrc] = rec
                print(f"{status:7s} {rec['file']}  start {rec['start']:.1f}s ({rec['method']})")
            except Exception as e:
                failed.append((j[0], j[2], j[3], str(e)[:200]))
    CHOSEN.write_text(json.dumps(dict(sorted(results.items(), key=lambda kv: (kv[1]["slug"], kv[1]["track"]))), indent=1, ensure_ascii=False) + "\n")
    total = sum(p.stat().st_size for p in OUT.rglob("*.mp3"))
    print(f"clips: {sum(1 for _ in OUT.rglob('*.mp3'))} | total {total / 1e6:.1f} MB | failed: {failed or 'none'} | no audio: {missing or 'none'}")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
