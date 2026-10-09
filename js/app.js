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

  // Analytics (GoatCounter, only when content/site_config.json sets goatcounter_code; no cookies). Every call is
  // guarded, so nothing breaks when the script is absent, blocked or still loading.
  var track = function (path, title) {
    try {
      var gc = window.goatcounter;
      if (gc && typeof gc.count === "function") gc.count({ path: path, title: title || path, event: true });
    } catch (e) { /* ignore */ }
  };
  var slugify = function (s) { return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); };
  var relSlug = function (el) { var a = el && el.closest("[data-slug]"); return a ? a.getAttribute("data-slug") : ""; };
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a.store, a[data-gc]");
    if (!a) return;
    if (a.hasAttribute("data-gc")) { track(a.getAttribute("data-gc")); return; }
    var svc = slugify((a.firstChild && a.firstChild.nodeValue) || a.textContent);
    track("event/store/" + svc + "/" + relSlug(a));
  });
  each("details[data-isrc]", function (d) {
    d.addEventListener("toggle", function () {
      if (!d.open) return;
      var n = d.closest("li").querySelector(".n");
      track("event/lyrics/" + relSlug(d) + "/" + ("0" + (n ? n.textContent.trim() : "")).slice(-2));
    });
  });

  // Mobile menu (<=780px): the toggle opens the nav panel; Esc, an outside click or choosing a link closes it.
  var navBar = document.querySelector(".topbar"), tog = document.querySelector(".nav-toggle");
  if (navBar && tog) {
    var setOpen = function (on, focusBack) {
      navBar.classList.toggle("nav-open", on); tog.setAttribute("aria-expanded", on ? "true" : "false");
      if (on) { var a = navBar.querySelector("nav a"); if (a) a.focus(); } else if (focusBack) tog.focus();
    };
    tog.addEventListener("click", function () { setOpen(!navBar.classList.contains("nav-open")); });
    each("nav a", function (a) { a.addEventListener("click", function () { setOpen(false); }); }, navBar);
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && navBar.classList.contains("nav-open")) setOpen(false, true); });
    document.addEventListener("click", function (ev) { if (navBar.classList.contains("nav-open") && !navBar.contains(ev.target)) setOpen(false); });
  }

  // "More" store buttons: extras are hidden by CSS (only when JS runs); the toggle reveals them.
  each(".store-more", function (b) {
    var ul = document.getElementById(b.getAttribute("aria-controls")); if (!ul) return;
    var n = b.querySelector(".more-n");
    b.addEventListener("click", function () {
      var open = ul.hasAttribute("data-collapsed");
      if (open) ul.removeAttribute("data-collapsed"); else ul.setAttribute("data-collapsed", "");
      b.setAttribute("aria-expanded", open ? "true" : "false");
      b.firstChild.nodeValue = open ? "Fewer" : "More";
      if (n) n.hidden = open;
      if (open) { var first = ul.querySelector(".store-extra a"); if (first) first.focus(); }
    });
  });

  // 30-second previews: one shared <audio preload="none">, so only one clip plays at a time and nothing
  // downloads until a play button is pressed.
  var pvButtons = document.querySelectorAll("button.pv");
  var top = document.querySelector("button.pv-top");
  if (pvButtons.length) {
    var audio = new Audio(); audio.preload = "none";
    var current = null;   // the .pv button whose clip is loaded
    var main = top && top.closest(".pv-main");
    var nowEl = main && main.querySelector(".pv-now"), timeEl = main && main.querySelector(".pv-time");
    var mmss = function (t) { t = Math.max(0, Math.floor(t || 0)); return Math.floor(t / 60) + ":" + ("0" + t % 60).slice(-2); };
    var label = function (btn, playing) {
      btn.setAttribute("aria-label", (playing ? "Pause" : "Play") + " 30-second preview of " + btn.getAttribute("data-title"));
    };
    var setState = function (playing) {
      if (current) {
        current.classList.toggle("is-playing", playing);
        label(current, playing);
        current.closest("li").classList.toggle("pv-active", true);
      }
      if (top) {
        top.classList.toggle("is-playing", playing);
        var title = current ? current.getAttribute("data-title") : pvButtons[0].getAttribute("data-title");
        top.setAttribute("aria-label", (playing ? "Pause" : "Play") + " 30-second preview of " + title);
        top.querySelector(".pv-top-label").textContent = playing ? "Pause preview" : "Play preview";
        if (nowEl) nowEl.textContent = title;
      }
    };
    var progress = function () {
      if (!current) return;
      var d = audio.duration || 30, p = Math.min(1, (audio.currentTime || 0) / d);
      var bar = current.closest("li").querySelector(".pv-bar > span");
      if (bar) bar.style.transform = "scaleX(" + p + ")";
      if (timeEl) timeEl.textContent = mmss(audio.currentTime) + " / " + mmss(d);
    };
    var reset = function (btn) {
      if (!btn) return;
      btn.classList.remove("is-playing"); label(btn, false);
      var li = btn.closest("li"); li.classList.remove("pv-active");
      var bar = li.querySelector(".pv-bar > span"); if (bar) bar.style.transform = "scaleX(0)";
    };
    var play = function (btn) {
      if (current === btn && !audio.paused) { audio.pause(); return; }
      var fresh = current !== btn || audio.ended || audio.currentTime < 0.5;
      if (current !== btn) {
        reset(current); current = btn;
        audio.src = btn.getAttribute("data-src");
      }
      if (fresh) {   // a clip starting (not a resume after pause)
        var m = /previews\/([^\/]+)\/(\d+)\.mp3/.exec(btn.getAttribute("data-src") || "");
        if (m) track("event/play/" + m[1] + "/" + m[2]);
      }
      var pr = audio.play();
      if (pr && pr.catch) pr.catch(function () { setState(false); });
    };
    Array.prototype.forEach.call(pvButtons, function (btn) {
      btn.addEventListener("click", function () { play(btn); });
    });
    if (top) top.addEventListener("click", function () { play(current || pvButtons[0]); });
    audio.addEventListener("play", function () { setState(true); });
    audio.addEventListener("pause", function () { setState(false); });
    audio.addEventListener("timeupdate", progress);
    audio.addEventListener("ended", function () {
      setState(false); reset(current); audio.currentTime = 0; if (timeEl) timeEl.textContent = "0:00 / 0:30";
    });
    audio.addEventListener("error", function () {
      if (!current) return;
      setState(false); if (nowEl) nowEl.textContent = "Preview unavailable";
    });
    document.addEventListener("keydown", function (ev) {   // Esc stops the preview
      if (ev.key === "Escape" && !audio.paused) audio.pause();
    });
  }

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
