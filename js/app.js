/* bfo.mantis — progressive enhancement only. Pages are pre-rendered by tools/build_pages.py. */
(function () {
  "use strict";
  var today = new Date(); today.setHours(0, 0, 0, 0);
  var each = function (sel, fn, root) { Array.prototype.forEach.call((root || document).querySelectorAll(sel), fn); };
  var y = document.getElementById("year"); if (y) y.textContent = new Date().getFullYear();

  // Upcoming vs released labels are baked in at build time; refresh them against today's date.
  each("[data-date]", function (el) {
    var p = el.getAttribute("data-date").split("-");
    var up = new Date(+p[0], p[1] - 1, +p[2]) > today;
    // only touch the DOM when the baked-in state is out of date (avoids needless style recalcs)
    each(".js-upcoming", function (x) { if (x.hidden !== !up && x.closest("[data-date]") === el) x.hidden = !up; }, el);
    each(".js-released", function (x) { if (x.hidden !== up && x.closest("[data-date]") === el) x.hidden = up; }, el);
  });

  // Compact header + back-to-top button once the page is scrolled.
  var body = document.body, ticking = false, st = {};
  var set = function (cls, on) { if (st[cls] !== on) { st[cls] = on; body.classList.toggle(cls, on); } };
  var onScroll = function () {
    ticking = false;
    var s = window.pageYOffset;
    set("is-scrolled", s > 24);
    set("show-top", s > 900);
  };
  var queue = function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } };
  window.addEventListener("scroll", queue, { passive: true });
  window.addEventListener("load", queue);   // e.g. reload mid-page (reading the offset earlier would force a layout)
  each('a[href="#top"]', function (a) {
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
      var brand = document.querySelector(".brand"); if (brand) brand.focus({ preventScroll: true });
      if (history.replaceState) history.replaceState(null, "", location.pathname + location.search);
    });
  });

  // Lyrics: fetched only when a track is first expanded (keeps the page light).
  var rel = document.querySelector("article.release[data-lyrics]");
  if (rel) {
    var file = rel.getAttribute("data-lyrics"), lyricsPromise = null;
    // A track is a plain string, or (when it has redactions) an array of lines; a line is a string or an
    // array of parts, where a part is a string or {r: n} (a redaction of roughly n characters, bucketed).
    // Redactions render as empty bars: no text inside, so nothing can be selected, copied or searched.
    var bar = function (n, whole) {
      var b = document.createElement("span");
      b.className = "rbar" + (whole ? " rbar-line" : "");
      b.setAttribute("role", "img");
      b.setAttribute("aria-label", "redacted");
      b.style.setProperty("--n", Math.max(1, Math.min(64, +n || 8)));
      return b;
    };
    var renderLyrics = function (box, v) {
      box.textContent = "";
      if (!v) { box.textContent = "Lyrics unavailable."; return; }
      if (typeof v === "string") { box.textContent = v; return; }   // textContent: no HTML injection
      v.forEach(function (line, i) {
        if (i) box.appendChild(document.createTextNode("\n"));
        if (typeof line === "string") { box.appendChild(document.createTextNode(line)); return; }
        var whole = line.length === 1 && typeof line[0] === "object";
        line.forEach(function (p) {
          box.appendChild(typeof p === "string" ? document.createTextNode(p) : bar(p && p.r, whole));
        });
      });
    };
    var loadLyrics = function () {
      if (!lyricsPromise) lyricsPromise = fetch(file).then(function (res) {
        if (!res.ok) throw new Error(res.status); return res.json();
      });
      return lyricsPromise;
    };
    each("details[data-isrc]", function (d) {
      d.addEventListener("toggle", function () {
        if (!d.open || d.dataset.loaded) return;
        var box = d.querySelector(".lyrics");
        loadLyrics().then(function (map) {
          renderLyrics(box, map[d.dataset.isrc]);
          d.dataset.loaded = "1";
        }).catch(function () { box.textContent = "Couldn't load lyrics. Please try again."; lyricsPromise = null; });
      });
    }, rel);
  }
})();
