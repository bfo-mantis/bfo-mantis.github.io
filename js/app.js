(function () {
  "use strict";
  var data = window.BFO_DATA || { releases: [] };
  var all = data.releases.slice();
  var today = new Date(); today.setHours(0, 0, 0, 0);
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var dateOf = function (r) { var p = r.release_date.split("-"); return new Date(+p[0], p[1] - 1, +p[2]); };
  var upcoming = function (r) { return dateOf(r) > today; };
  var fmt = function (r) { return dateOf(r).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }); };
  var link = function (r) { return "release.html?r=" + encodeURIComponent(r.slug); };
  var y = $("year"); if (y) y.textContent = new Date().getFullYear();

  function picture(r, small, eager, cls) {
    if (!r.cover) return '<div class="noart" aria-hidden="true"></div>';
    var webp = small ? r.cover.webp_small : r.cover.webp, jpg = small ? r.cover.jpg_small : r.cover.jpg;
    return '<picture><source type="image/webp" srcset="' + webp + '"><img ' + (cls ? 'class="' + cls + '" ' : "") +
      'src="' + jpg + '" width="' + (small ? 400 : 800) + '" height="' + (small ? 400 : 800) + '" alt="Cover art for ' + esc(r.title) + ' by bfo.mantis"' +
      (eager ? ' fetchpriority="high"' : ' loading="lazy" decoding="async"') + "></picture>";
  }
  function card(r, eager) {
    var n = r.tracks.length;
    var sub = (r.type === "album" ? n + (n === 1 ? " track" : " tracks") + " · " : "") + fmt(r) + (r.genre ? " · " + esc(r.genre) : "");
    return '<li class="card"><a href="' + link(r) + '">' +
      '<div class="art">' + picture(r, true, eager) + (upcoming(r) ? '<span class="badge">Out ' + fmt(r).replace(/, \d{4}$/, "") + "</span>" : "") + "</div>" +
      '<div class="info"><h3 class="title">' + esc(r.title) + '</h3><p class="sub">' + sub + "</p></div></a></li>";
  }

  // ---------- home ----------
  if ($("albums-grid")) {
    var albums = all.filter(function (r) { return r.type === "album"; });
    var singles = all.filter(function (r) { return r.type === "single"; });
    $("albums-grid").innerHTML = albums.map(function (r, i) { return card(r, i < 4); }).join("");
    $("singles-grid").innerHTML = singles.map(function (r) { return card(r, false); }).join("");
    $("albums-count").textContent = albums.length + " albums";
    $("singles-count").textContent = singles.length + " singles";
    var tracks = all.reduce(function (a, r) { return a + r.tracks.length; }, 0);
    $("hero-meta").textContent = albums.length + " albums · " + singles.length + " singles · " + tracks + " tracks";
    var released = all.filter(function (r) { return !upcoming(r); });
    var latest = all[0];
    if (latest) {
      $("hero-latest").outerHTML = '<a class="hero-latest" href="' + link(latest) + '">' + picture(latest, true, true) +
        '<div><div class="k">' + (upcoming(latest) ? "Out " + fmt(latest) : "Latest release") + '</div><div class="t">' + esc(latest.title) +
        '</div><div class="s">' + (latest.type === "album" ? "Album" : "Single") + (latest.genre ? " · " + esc(latest.genre) : "") + "</div></div></a>";
    }
    var bg = $("hero-bg");
    if (bg) bg.innerHTML = released.concat(released).slice(0, 24).map(function (r) {
      return r.cover ? '<img src="' + r.cover.jpg_small + '" alt="" loading="lazy" decoding="async" width="400" height="400">' : "";
    }).join("");
  }

  // ---------- release ----------
  var el = $("release");
  if (el) {
    var slug = new URLSearchParams(location.search).get("r");
    var r = all.filter(function (x) { return x.slug === slug; })[0];
    if (!r) {
      document.title = "Release not found — bfo.mantis";
      el.innerHTML = '<div class="notfound"><h1>Release not found</h1><p><a class="back" href="./">← Back to all releases</a></p></div>';
      return;
    }
    document.title = r.title + " — bfo.mantis";
    var md = document.createElement("meta"); md.name = "description";
    md.content = r.title + " by bfo.mantis — " + (r.type === "album" ? "album" : "single") + ", " + r.release_date_display + "."; document.head.appendChild(md);
    if (r.cover) $("release-bg").style.backgroundImage = 'url("' + r.cover.jpg_small + '")';
    var NT = '<span class="sr-only"> (opens in a new tab)</span>';
    var primaryLabel = r.listen_source === "hyperfollow" ? (upcoming(r) ? "Pre-save / listen" : "Listen everywhere") : "Listen";
    var listen = r.listen_url
      ? '<a class="btn" href="' + esc(r.listen_url) + '" target="_blank" rel="noopener">' +
        '<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>' + primaryLabel + NT + "</a>"
      : "";
    var stores = (r.store_links || []).filter(function (st) { return st.url !== r.listen_url; });
    if (stores.length) {
      listen += '<div class="stores"><p class="stores-label" id="stores-label">Or open in</p><ul class="store-row" aria-labelledby="stores-label">' +
        stores.map(function (st) {
          return '<li><a class="store" href="' + esc(st.url) + '" target="_blank" rel="noopener">' + esc(st.name) + NT + "</a></li>";
        }).join("") + "</ul></div>";
    }
    el.innerHTML =
      '<div class="cover-col"><div class="cover">' + picture(r, false, true) + "</div>" +
      '<p class="art-copy">Artwork &copy; ' + r.release_date.slice(0, 4) + " bfo.mantis Records. All rights reserved.</p></div>" +
      "<div>" +
      '<a class="back" href="./#' + (r.type === "album" ? "albums" : "singles") + '">← All releases</a>' +
      '<p class="eyebrow">' + (r.type === "album" ? "Album" : "Single") + (upcoming(r) ? " · Upcoming" : "") + "</p>" +
      "<h1>" + esc(r.title) + "</h1>" +
      '<p class="by">bfo.mantis</p>' +
      '<ul class="facts">' +
      '<li><span>Released</span> ' + (upcoming(r) ? "Out " : "") + '<time datetime="' + r.release_date + '">' + esc(r.release_date_display) + "</time></li>" +
      (r.genre ? "<li><span>Genre</span> " + esc(r.genre) + "</li>" : "") +
      "<li>" + r.tracks.length + (r.tracks.length === 1 ? " track" : " tracks") + "</li>" +
      (r.label ? "<li><span>Label</span> " + esc(r.label) + "</li>" : "") +
      "</ul>" + listen +
      '<h2 class="tracks-title">Tracklist</h2>' +
      '<ol class="tracks">' + r.tracks.map(function (t) {
        if (t.lyrics === "lyrics" && r.lyrics_file) {
          return '<li class="has-lyrics"><span class="n">' + t.n + '</span><details data-isrc="' + esc(t.isrc) + '">' +
            '<summary><span class="tt">' + esc(t.title) + '</span><span class="ltag" aria-hidden="true">Lyrics</span>' +
            '<span class="sr-only"> — show lyrics</span></summary>' +
            '<div class="lyrics" aria-live="polite">Loading lyrics…</div>' +
            '<p class="lcopy">&copy; ' + r.release_date.slice(0, 4) + ' bfo.mantis Records. All rights reserved.</p></details></li>';
        }
        return '<li><span class="n">' + t.n + '</span><span class="tt">' + esc(t.title) +
          (t.lyrics === "instrumental" ? ' <span class="itag">Instrumental</span>' : "") + "</span></li>";
      }).join("") + "</ol>" +
      "</div>";
    // Lyrics are fetched only when a track is first expanded (keeps the initial page light).
    var lyricsPromise = null;
    var loadLyrics = function () {
      if (!lyricsPromise) lyricsPromise = fetch(r.lyrics_file).then(function (res) {
        if (!res.ok) throw new Error(res.status); return res.json();
      });
      return lyricsPromise;
    };
    Array.prototype.forEach.call(el.querySelectorAll("details[data-isrc]"), function (d) {
      d.addEventListener("toggle", function () {
        if (!d.open || d.dataset.loaded) return;
        var box = d.querySelector(".lyrics");
        loadLyrics().then(function (map) {
          box.textContent = map[d.dataset.isrc] || "Lyrics unavailable.";   // textContent: no HTML injection
          d.dataset.loaded = "1";
        }).catch(function () { box.textContent = "Couldn't load lyrics. Please try again."; lyricsPromise = null; });
      });
    });
    var more = all.filter(function (x) { return x.slug !== r.slug && x.type === r.type; }).slice(0, 6);
    if (more.length) {
      $("more-title").textContent = "More " + (r.type === "album" ? "albums" : "singles");
      $("more-grid").innerHTML = more.map(function (x) { return card(x, false); }).join("");
      $("more-section").hidden = false;
    }
  }
})();
