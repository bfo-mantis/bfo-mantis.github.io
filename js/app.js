/* bfo.mantis — progressive enhancement only. Pages are pre-rendered by tools/build_pages.py. */
(function () {
  "use strict";
  var each = function (sel, fn, root) { Array.prototype.forEach.call((root || document).querySelectorAll(sel), fn); };
  var narrow = window.matchMedia ? matchMedia("(max-width: 960px)") : null;

  // Per-page listeners on window/document are bound through on(), tied to an AbortController that is aborted when
  // client-side navigation swaps the page, so re-running init() never stacks duplicate handlers.
  var sigOK = false;
  try { var tac = new AbortController(); window.addEventListener("bfo-test", null, { get signal() { sigOK = true; return tac.signal; } }); } catch (err) { sigOK = false; }
  var pageAC = null;
  var on = function (t, type, fn, o) {
    o = o || {};
    if (pageAC) o.signal = pageAC.signal;
    t.addEventListener(type, fn, o);
  };

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

  document.addEventListener("submit", function (ev) {   // email sign-up (only live when email_signup_url is configured)
    var f = ev.target;
    if (f && f.hasAttribute && f.hasAttribute("data-gc")) track(f.getAttribute("data-gc"));
  });

  // ---------- 30-second previews + the site-wide mini-player ----------
  // One shared <audio preload="none"> for the whole visit, so only one clip plays at a time and nothing downloads until
  // a play button is pressed. The player (audio + bottom bar) lives outside the page content: while a clip is loaded,
  // internal links swap pages client-side (see the router below), so it keeps playing as you browse.
  var svgPlay = '<svg class="i-play" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z" fill="currentColor"/></svg>';
  var svgPause = '<svg class="i-pause" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor"/></svg>';
  var mmss = function (t) { t = Math.max(0, Math.floor(t || 0)); return Math.floor(t / 60) + ":" + ("0" + t % 60).slice(-2); };
  var abs = function (u) { try { return u ? new URL(u, location.href).href : ""; } catch (err) { return ""; } };
  var noop = function () {};
  var PL = {
    audio: null, it: null,          // it: the loaded clip {src, title, rel, href, art} (absolute URLs)
    q: null, qi: -1, qname: "",     // an optional queue (e.g. the Start here ten)
    mini: null, page: null          // page: hooks the current page registers (button states, progress bars)
  };
  var hooks = function () { return PL.page || { state: noop, progress: noop, changed: noop, ended: noop, error: noop, closed: noop }; };
  PL.itemFrom = function (btn) {
    return { src: abs(btn.getAttribute("data-src")), title: btn.getAttribute("data-title") || "", rel: btn.getAttribute("data-rel") || "",
      href: abs(btn.getAttribute("data-href")), art: abs(btn.getAttribute("data-art")) };
  };
  PL.active = function () { return !!(PL.audio && PL.it && PL.mini && !PL.mini.hidden); };
  PL.playing = function () { return !!(PL.audio && !PL.audio.paused); };
  var mEls = {};
  var buildMini = function () {
    var m = document.createElement("div");
    m.className = "mini"; m.hidden = true;
    m.setAttribute("role", "region"); m.setAttribute("aria-label", "Preview player");
    m.innerHTML = '<img class="mini-art" alt="" width="44" height="44"><div class="mini-meta"><span class="mini-t"></span><span class="mini-s"></span></div>' +
      '<span class="mini-time" aria-hidden="true">0:00 / 0:30</span>' +
      '<button type="button" class="mini-pp" aria-label="Pause preview">' + svgPlay + svgPause + '</button>' +
      '<button type="button" class="mini-nx" hidden aria-label="Next in queue"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5.5v13l9-6.5zM16.5 5.5H19v13h-2.5z" fill="currentColor"/></svg></button>' +
      '<button type="button" class="mini-x" aria-label="Close preview player"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg></button>' +
      '<span class="mini-prog" aria-hidden="true"><span></span></span>';
    document.body.appendChild(m);
    PL.mini = m;
    ["pp", "nx", "t", "s", "art", "time"].forEach(function (k) { mEls[k] = m.querySelector(".mini-" + k); });
    mEls.bar = m.querySelector(".mini-prog > span");
    mEls.pp.addEventListener("click", function () { if (PL.it) PL.play(PL.it); });
    mEls.nx.addEventListener("click", function () { PL.next(); });
    m.querySelector(".mini-x").addEventListener("click", function () { PL.close(); });
  };
  PL.showMini = function () {   // (re)draw the bar for the loaded clip; also called after each page swap
    var it = PL.it; if (!it) return;
    if (!PL.mini) buildMini();
    mEls.t.textContent = it.title;
    mEls.s.textContent = "";
    var qtxt = PL.q ? PL.qname + " · " + (PL.qi + 1) + " of " + PL.q.length : "";
    if (it.rel && it.href && location.pathname.replace(/index\.html$/, "") !== new URL(it.href).pathname) {
      var a = document.createElement("a"); a.href = it.href; a.textContent = it.rel; mEls.s.appendChild(a);
      if (qtxt) mEls.s.appendChild(document.createTextNode(" · " + qtxt));
    } else mEls.s.textContent = qtxt || (it.rel ? it.rel + " · 30s preview" : "30s preview");
    if (it.art) { if (mEls.art.getAttribute("src") !== it.art) mEls.art.src = it.art; mEls.art.hidden = false; } else mEls.art.hidden = true;
    var hasNext = !!(PL.q && PL.qi < PL.q.length - 1);
    mEls.nx.hidden = !hasNext; PL.mini.classList.toggle("has-q", hasNext);
    if (hasNext) mEls.nx.setAttribute("aria-label", "Next: " + PL.q[PL.qi + 1].title);
    if (PL.mini.hidden) PL.mini.hidden = false;
    document.body.classList.add("has-mini");
  };
  var miniState = function (playing) {
    if (!PL.mini || !PL.it) return;
    mEls.pp.classList.toggle("is-playing", playing);
    mEls.pp.setAttribute("aria-label", (playing ? "Pause" : "Play") + " preview of " + PL.it.title);
  };
  var miniProgress = function () {
    if (!PL.mini || PL.mini.hidden) return;
    var d = PL.audio.duration || 30;
    mEls.bar.style.transform = "scaleX(" + Math.min(1, (PL.audio.currentTime || 0) / d) + ")";
    mEls.time.textContent = mmss(PL.audio.currentTime) + " / " + mmss(d);
  };
  var qSync = function () { each("button.q-play", function (b) { var mine = PL.q && PL.qname === b.getAttribute("data-qname"); b.classList.toggle("is-playing", !!(mine && PL.playing())); }); };
  var ensureAudio = function () {
    if (PL.audio) return PL.audio;
    var audio = PL.audio = new Audio(); audio.preload = "none";
    audio.addEventListener("play", function () { hooks().state(true); PL.showMini(); miniState(true); qSync(); });
    audio.addEventListener("pause", function () { hooks().state(false); miniState(false); qSync(); });
    audio.addEventListener("timeupdate", function () { hooks().progress(); miniProgress(); });
    audio.addEventListener("ended", function () {
      if (PL.q && PL.qi < PL.q.length - 1) { PL.next(); return; }
      hooks().ended(); miniState(false); audio.currentTime = 0;
      if (mEls.bar) mEls.bar.style.transform = "scaleX(0)";
      if (PL.q) { PL.q = null; PL.qi = -1; PL.showMini(); }
      qSync();
    });
    audio.addEventListener("error", function () {
      if (!PL.it) return;
      hooks().error(); miniState(false); qSync();
    });
    document.addEventListener("keydown", function (ev) {   // Esc stops the preview (unless it is closing the lightbox)
      if (ev.key === "Escape" && !audio.paused && !document.querySelector("dialog[open]")) audio.pause();
    });
    return audio;
  };
  // Play (or pause/resume) a clip. qi: its index when it is played as part of PL.q; any other clip ends the queue.
  PL.play = function (it, qi) {
    var audio = ensureAudio();
    var same = PL.it && PL.it.src === it.src;
    if (same && !audio.paused && qi === undefined) { audio.pause(); return; }
    var fresh = !same || audio.ended || audio.currentTime < 0.5;
    if (qi !== undefined) PL.qi = qi; else if (!same) { PL.q = null; PL.qi = -1; }
    if (!same) {
      var old = PL.it; PL.it = it;
      audio.src = it.src;
      hooks().changed(old);
    }
    if (fresh) {   // a clip starting (not a resume after pause)
      var m = /previews\/([^\/]+)\/(\d+)\.mp3/.exec(it.src || "");
      if (m) track("event/play/" + m[1] + "/" + m[2]);
    }
    if (PL.mini && !PL.mini.hidden) PL.showMini();
    var pr = audio.play();
    if (pr && pr.catch) pr.catch(function () { hooks().state(false); miniState(false); qSync(); });
  };
  PL.next = function () { if (PL.q && PL.qi < PL.q.length - 1) PL.play(PL.q[PL.qi + 1], PL.qi + 1); };
  PL.close = function () {
    if (!PL.audio) return;
    PL.audio.pause();
    var old = PL.it;
    hooks().state(false); hooks().ended(); PL.audio.currentTime = 0;
    PL.q = null; PL.qi = -1;
    if (PL.mini) { PL.mini.hidden = true; document.body.classList.remove("has-mini"); }
    qSync();
    hooks().closed(old);
  };

  // ---------- per-page setup (re-run after each client-side page swap) ----------
  var init = function () {
  pageAC = sigOK ? new AbortController() : null;
  var today = new Date(); today.setHours(0, 0, 0, 0);
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
  on(window, "scroll", queue, { passive: true });
  if (document.readyState === "complete") queue(); else on(window, "load", queue);   // e.g. reload mid-page (reading the offset earlier would force a layout)
  each('a[href="#top"]', function (a) {
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
      var brand = document.querySelector(".brand"); if (brand) brand.focus({ preventScroll: true });
      if (history.replaceState) history.replaceState(null, "", location.pathname + location.search);
    });
  });

  // Analytics: lyric / "more about" expands (the click and submit counters are bound once, outside init)
  each("details[data-isrc]", function (d) {
    d.addEventListener("toggle", function () {
      if (!d.open) return;
      var n = d.closest("li").querySelector(".n");
      track("event/lyrics/" + relSlug(d) + "/" + ("0" + (n ? n.textContent.trim() : "")).slice(-2));
    });
  });
  each("details.tmore", function (d) {
    d.addEventListener("toggle", function () {
      if (!d.open) return;
      var n = d.closest("li").querySelector(".n");
      track("event/blurb/" + relSlug(d) + "/" + ("0" + (n ? n.textContent.trim() : "")).slice(-2));
    });
  });

  // Mobile menu (<=960px): the toggle opens the nav panel; Esc, an outside click or choosing a link closes it.
  var navBar = document.querySelector(".topbar"), tog = document.querySelector(".nav-toggle");
  if (navBar && tog) {
    var setOpen = function (on, focusBack) {
      navBar.classList.toggle("nav-open", on); tog.setAttribute("aria-expanded", on ? "true" : "false");
      if (on) { var a = navBar.querySelector("nav a"); if (a) a.focus(); } else if (focusBack) tog.focus();
    };
    tog.addEventListener("click", function () { setOpen(!navBar.classList.contains("nav-open")); });
    each("nav a", function (a) { a.addEventListener("click", function () { setOpen(false); }); }, navBar);
    on(document, "keydown", function (ev) { if (ev.key === "Escape" && navBar.classList.contains("nav-open")) setOpen(false, true); });
    on(document, "click", function (ev) { if (navBar.classList.contains("nav-open") && !navBar.contains(ev.target)) setOpen(false); });
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

  // Previews on this page: the buttons drive the shared player (PL); PL calls back through these hooks.
  PL.page = null;
  var pvButtons = document.querySelectorAll("button.pv");
  var top = document.querySelector("button.pv-top");
  var main = top && top.closest(".pv-main");
  var fab = null, mainOut = false;
  var fabUpdate = function () {
    if (!fab) return;
    var on_ = mainOut && !PL.active() && narrow && narrow.matches;
    fab.classList.toggle("is-on", !!on_);
    fab.tabIndex = on_ ? 0 : -1; fab.setAttribute("aria-hidden", on_ ? "false" : "true");
    body.classList.toggle("has-fab", !!on_);
  };
  if (pvButtons.length) {
    var nowEl = main && main.querySelector(".pv-now"), timeEl = main && main.querySelector(".pv-time");
    var cur = function () {   // this page's button for the loaded clip, if any
      if (!PL.it) return null;
      for (var i = 0; i < pvButtons.length; i++) if (abs(pvButtons[i].getAttribute("data-src")) === PL.it.src) return pvButtons[i];
      return null;
    };
    var label = function (btn, playing) {
      btn.setAttribute("aria-label", (playing ? "Pause" : "Play") + " 30-second preview of " + btn.getAttribute("data-title"));
    };
    var setState = function (playing) {
      var c = cur();
      if (c) {
        c.classList.toggle("is-playing", playing);
        label(c, playing);
        c.closest("li").classList.toggle("pv-active", true);
      }
      if (top) {
        var shown = c || pvButtons[0], tp = playing && !!c;
        top.classList.toggle("is-playing", tp);
        top.setAttribute("aria-label", (tp ? "Pause" : "Play") + " 30-second preview of " + shown.getAttribute("data-title"));
        top.querySelector(".pv-top-label").textContent = tp ? "Pause preview" : "Play preview";
        if (nowEl) nowEl.textContent = shown.getAttribute("data-title");
      }
    };
    var reset = function (btn) {
      if (!btn) return;
      btn.classList.remove("is-playing"); label(btn, false);
      var li = btn.closest("li"); li.classList.remove("pv-active");
      var bar = li.querySelector(".pv-bar > span"); if (bar) bar.style.transform = "scaleX(0)";
    };
    var btnFor = function (it) {
      if (!it) return null;
      for (var i = 0; i < pvButtons.length; i++) if (abs(pvButtons[i].getAttribute("data-src")) === it.src) return pvButtons[i];
      return null;
    };
    PL.page = {
      state: setState,
      progress: function () {
        var c = cur(); if (!c) return;
        var d = PL.audio.duration || 30, p = Math.min(1, (PL.audio.currentTime || 0) / d);
        var bar = c.closest("li").querySelector(".pv-bar > span");
        if (bar) bar.style.transform = "scaleX(" + p + ")";
        if (timeEl) timeEl.textContent = mmss(PL.audio.currentTime) + " / " + mmss(d);
      },
      changed: function (old) { reset(btnFor(old)); if (timeEl) timeEl.textContent = "0:00 / 0:30"; setState(false); fabUpdate(); },
      ended: function () { setState(false); reset(cur()); if (timeEl) timeEl.textContent = "0:00 / 0:30"; },
      error: function () { setState(false); if (nowEl && cur()) nowEl.textContent = "Preview unavailable"; },
      closed: function (old) {
        if (timeEl) timeEl.textContent = "0:00 / 0:30";
        fabUpdate();
        var b = btnFor(old);
        if (b && b.offsetParent) b.focus(); else if (top) top.focus();
      }
    };
    Array.prototype.forEach.call(pvButtons, function (btn) {
      btn.addEventListener("click", function () { PL.play(PL.itemFrom(btn)); });
    });
    if (top) top.addEventListener("click", function () { PL.play(PL.itemFrom(cur() || pvButtons[0])); });

    // Phones: a floating "Play latest" / "Play preview" button once the page's main player has scrolled out of view
    // (hidden while the mini-player is open). The page gets matching bottom padding so nothing ends up underneath it.
    if (main) {
      fab = document.createElement("button");
      fab.type = "button"; fab.className = "fab-play"; fab.tabIndex = -1; fab.setAttribute("aria-hidden", "true");
      fab.innerHTML = svgPlay + "<span></span>";
      fab.querySelector("span").textContent = main.getAttribute("data-fab") || "Play preview";
      document.body.appendChild(fab);
      fab.addEventListener("click", function () { PL.play(PL.itemFrom(cur() || pvButtons[0])); });
      // the main player counts as "out of view" once it has scrolled above the viewport (rAF-throttled, read-only)
      var fabTick = false;
      var fabCheck = function () {
        fabTick = false;
        if (!narrow || !narrow.matches) { if (mainOut) { mainOut = false; fabUpdate(); } return; }
        var out = main.getBoundingClientRect().bottom < 72;   // i.e. behind or above the sticky header
        if (out !== mainOut) { mainOut = out; fabUpdate(); }
      };
      on(window, "scroll", function () { if (!fabTick) { fabTick = true; requestAnimationFrame(fabCheck); } }, { passive: true });
      if (document.readyState === "complete") fabCheck(); else on(window, "load", fabCheck);
      if (narrow && narrow.addEventListener) on(narrow, "change", fabCheck);
    }
    // arriving on a page while a clip is loaded (client-side navigation): mark its button
    if (PL.it) { var c0 = cur(); if (c0) { setState(PL.playing()); PL.page.progress(); } }
  }
  // Queues ("Play the Start here ten"): the button carries the list; the mini-player shows "n of 10" and a Next button.
  each("button.q-play", function (b) {
    b.addEventListener("click", function () {
      var name = b.getAttribute("data-qname") || "Queue";
      if (PL.q && PL.qname === name) { if (PL.playing()) PL.audio.pause(); else PL.play(PL.it, PL.qi); return; }
      var list; try { list = JSON.parse(b.getAttribute("data-queue")); } catch (err) { return; }
      if (!list || !list.length) return;
      PL.q = list.map(function (x) { return { src: abs(x.src), title: x.title || "", rel: x.rel || "", href: abs(x.href), art: abs(x.art) }; });
      PL.qname = name;
      track("event/queue/" + (b.getAttribute("data-gcq") || "start"));
      PL.play(PL.q[0], 0);
    });
  });
  qSync();
  if (PL.active()) { PL.showMini(); miniState(PL.playing()); }
  fabUpdate();

  // Cover lightbox (release pages): the cover links to the 800px JPG; with JS it opens in a modal <dialog> instead.
  // Esc and the close button close it; Tab stays inside; focus returns to the cover link.
  each("a[data-lightbox]", function (a) {
    var dlg = document.getElementById(a.getAttribute("data-lightbox"));
    if (!dlg || typeof dlg.showModal !== "function") return;
    var img = dlg.querySelector("img"), close = dlg.querySelector(".lb-close");
    a.addEventListener("click", function (ev) {
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;   // let "open in new tab" work
      ev.preventDefault();
      if (!img.getAttribute("src")) img.src = img.getAttribute("data-src");
      dlg.showModal(); close.focus();
      track("event/cover/" + relSlug(a));
    });
    close.addEventListener("click", function () { dlg.close(); });
    dlg.addEventListener("click", function (ev) { if (ev.target === dlg) dlg.close(); });   // backdrop
    dlg.addEventListener("close", function () { a.focus(); });
    dlg.addEventListener("keydown", function (ev) {
      if (ev.key !== "Tab") return;
      var f = dlg.querySelectorAll("button, [href], [tabindex]:not([tabindex='-1'])");
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    });
  });

  // Nav "Support" group (Donate + Other ways to help): a disclosure on wide screens; flat inside the phone menu.
  each(".nav-group", function (g) {
    var b = g.querySelector(".nav-sub-btn"); if (!b) return;
    var setG = function (on, focusBtn) { g.classList.toggle("is-open", on); b.setAttribute("aria-expanded", on ? "true" : "false"); if (!on && focusBtn) b.focus(); };
    b.addEventListener("click", function () { var on = !g.classList.contains("is-open"); setG(on); if (on) { var a = g.querySelector(".nav-sub a"); if (a) a.focus(); } });
    g.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && g.classList.contains("is-open")) { ev.stopPropagation(); setG(false, true); } });
    g.addEventListener("focusout", function (ev) { if (!g.contains(ev.relatedTarget)) setG(false); });
    on(document, "click", function (ev) { if (!g.contains(ev.target)) setG(false); });
    each("a", function (a) { a.addEventListener("click", function () { setG(false); }); }, g);
  });

  // Share buttons: Web Share API where available, otherwise copy the link. Counted as event/share/<slug>.
  each(".share-btn", function (b) {
    var status = b.parentNode.querySelector(".share-status"), t = null;
    var say = function (m) { if (!status) return; status.textContent = m; clearTimeout(t); t = setTimeout(function () { status.textContent = ""; }, 4000); };
    b.addEventListener("click", function () {
      var url = b.getAttribute("data-share-url"), title = b.getAttribute("data-share-title");
      track("event/share/" + (b.getAttribute("data-share-slug") || "site"));
      if (navigator.share) {
        navigator.share({ title: title, url: url }).catch(function () { /* cancelled */ });
        return;
      }
      var fallback = function () {
        var i = document.createElement("input"); i.value = url; i.setAttribute("readonly", ""); i.style.position = "fixed"; i.style.opacity = "0";
        document.body.appendChild(i); i.select();
        var ok = false; try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
        document.body.removeChild(i);
        say(ok ? "Link copied" : "Copy this link: " + url);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(function () { say("Link copied"); }, fallback);
      else fallback();
    });
  });

  // Community: filter the country list and show the chosen country's card.
  var ccq = document.getElementById("cc-q"), ccList = document.getElementById("cc-list");
  if (ccq && ccList) {
    var ccBtns = ccList.querySelectorAll(".cc"), ccCount = document.getElementById("cc-count"), ccNone = document.getElementById("cc-none");
    var norm = function (t) { return String(t || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, ""); };
    ccq.addEventListener("input", function () {
      var q = norm(ccq.value.trim()), n = 0;
      Array.prototype.forEach.call(ccBtns, function (b) {
        var hit = !q || norm(b.getAttribute("data-name")).indexOf(q) > -1 || b.getAttribute("data-cc").toLowerCase() === q;
        b.parentNode.hidden = !hit; if (hit) n++;
      });
      ccCount.textContent = n + (n === 1 ? " country" : " countries");
      ccNone.hidden = n > 0;
    });
    var join = document.querySelector(".cc-join");
    Array.prototype.forEach.call(ccBtns, function (b) {
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(ccBtns, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        var name = b.getAttribute("data-name");
        document.getElementById("cc-flag").textContent = b.querySelector(".cc-flag").textContent;
        document.getElementById("cc-h").textContent = name;
        var ccp = document.getElementById("cc-p"), top_ = b.getAttribute("data-top");
        var card = document.getElementById("cc-card");
        ccp.textContent = card && card.getAttribute("data-room") === "discord"
          ? "Talk with fans of bfo.mantis in " + name + " on the bfo.mantis Discord."
          : "A room for fans of bfo.mantis in " + name + " to talk about their favorite songs.";
        if (top_) {
          ccp.appendChild(document.createTextNode(" bfo.mantis has listeners here. Most played: "));
          var ta = document.createElement("a"); ta.href = b.getAttribute("data-top-href"); ta.textContent = top_; ccp.appendChild(ta);
          ccp.appendChild(document.createTextNode("."));
        }
        if (join && join.tagName === "A") join.setAttribute("data-gc", (join.classList.contains("dc-btn") ? "event/discord/community/" : "event/community/") + b.getAttribute("data-cc").toLowerCase());
        if (narrow && narrow.matches) document.getElementById("cc-card").scrollIntoView({ block: "nearest" });
      });
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
    // Song pages (song/<slug>/): the lyrics box is shown open, so load it straight away.
    each(".song-lyrics[data-isrc]", function (box) {
      loadLyrics().then(function (map) { renderLyrics(box, map[box.getAttribute("data-isrc")]); })
        .catch(function () { box.textContent = "Couldn't load lyrics. Please reload the page."; lyricsPromise = null; });
    }, rel);
  }

  // Deep links to a track (#t3, used by search results): open its lyrics / "More about this track" and bring it into view.
  var openTrack = function () {
    var m = /^#t(\d+)$/.exec(location.hash); if (!m) return;
    var li = document.getElementById("t" + m[1]); if (!li) return;
    var d = li.querySelector("details"); if (d && !d.open) d.open = true;
    li.classList.add("t-hit"); setTimeout(function () { li.classList.remove("t-hit"); }, 2400);
    requestAnimationFrame(function () { li.scrollIntoView({ block: "center" }); });
  };
  openTrack(); on(window, "hashchange", openTrack);

  // Site search: the header button opens a modal <dialog>; the index (assets/data/search.json, built by
  // tools/build_pages.py from the published, already-redacted data) is fetched on first open. "/" or Ctrl/Cmd+K opens it.
  var sBtn = document.querySelector(".search-btn");
  if (sBtn && typeof document.createElement("dialog").showModal === "function") {
    var sRoot = sBtn.getAttribute("data-idx").replace(/assets\/data\/search\.json.*$/, "");
    var idx = null, idxP = null, sDlg, sIn, sOut, sStat, lastQ = "", tmr = 0;
    var norm = function (s) {
      return String(s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
        .replace(/['’`]/g, "").replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim();
    };
    var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
    var lev1 = function (a, b) {   // edit distance <= 1 (typo tolerance)
      if (a === b) return true;
      var la = a.length, lb = b.length; if (Math.abs(la - lb) > 1) return false;
      var i = 0, j = 0, d = 0;
      while (i < la && j < lb) {
        if (a[i] === b[j]) { i++; j++; continue; }
        if (++d > 1) return false;
        if (la > lb) i++; else if (lb > la) j++; else { i++; j++; }
      }
      return d + (la - i) + (lb - j) <= 1;
    };
    // token score against a normalized field: 3 = whole word, 2 = word prefix, 1 = inside a word / one typo away
    var tokScore = function (tok, f, words, fuzzy) {
      var at = f.indexOf(tok);
      if (at > -1) {
        var pre = at === 0 || f[at - 1] === " ", post = at + tok.length === f.length || f[at + tok.length] === " ";
        return pre && post ? 3 : pre ? 2 : 1;
      }
      if (fuzzy && tok.length >= 4) for (var k = 0; k < words.length; k++) if (words[k].length >= 4 && lev1(tok, words[k])) return 1;
      return 0;
    };
    var prep = function (d) {
      var R = d.r.map(function (r) {
        var o = { slug: r[0], title: r[1], type: r[2] === "a" ? "Album" : "Single", genre: r[3], year: r[4], art: r[5], blurb: r[6], instr: !!r[7] };
        o.f = [norm(o.title), norm([o.type, o.genre, o.year, o.instr ? "instrumental" : "songs"].join(" ")), norm(o.blurb)];
        return o;
      });
      var T = d.t.map(function (t) {
        var r = R[t[0]];
        var o = { r: r, n: t[1], title: t[2], kind: t[3], blurb: t[4], lyr: t[5] };
        o.f = [norm(o.title), norm([r.title, o.kind === "i" ? "instrumental" : "", r.genre].join(" ")), norm(o.blurb), norm(o.lyr)];
        return o;
      });
      var P = d.p.map(function (p) { var o = { title: p[0], path: p[1], desc: p[2] }; o.f = [norm(o.title), "", norm(o.desc)]; return o; });
      var all = [];
      [R, T, P].forEach(function (L) { L.forEach(function (o) { o.w = o.f.map(function (f) { return f ? f.split(" ") : []; }); all.push(o.f.join(" ")); }); });
      return { R: R, T: T, P: P, all: " " + all.join(" ") + " " };
    };
    var W = [10, 3, 1.5, 1];   // field weights: title, meta, blurb, lyrics
    var fz = [];   // per query word: allow one-typo matches only when the word appears nowhere in the index as typed
    var score = function (o, toks, qn) {
      var total = 0, best = -1;
      for (var i = 0; i < toks.length; i++) {
        var top = 0, tf = -1;
        for (var f = 0; f < o.f.length; f++) {
          if (!o.f[f]) continue;
          var s = tokScore(toks[i], o.f[f], o.w[f], fz[i]) * W[f];
          if (s > top) { top = s; tf = f; }
        }
        if (!top) return null;   // every word must match somewhere
        total += top; if (tf > best) best = tf;   // deepest field needed decides which snippet to show
      }
      if (o.f[0] === qn) total += 40; else if (o.f[0].indexOf(qn) === 0) total += 20; else if (toks.length > 1 && o.f[0].indexOf(qn) > -1) total += 12;
      for (var f2 = 2; f2 < o.f.length; f2++) if (toks.length > 1 && o.f[f2].indexOf(qn) > -1) total += 6 * W[f2];   // exact phrase
      return { s: total, field: best };
    };
    var hl = function (text, toks) {
      var out = esc(text);
      var parts = toks.filter(function (t) { return t.length > 1; }).sort(function (a, b) { return b.length - a.length; })
        .map(function (t) { return t.split("").map(function (c) { return c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }).join("['’]?"); });
      if (!parts.length) return out;
      return out.replace(new RegExp("(" + parts.join("|") + ")", "gi"), "<mark>$1</mark>");
    };
    var snippet = function (text, toks, qn) {   // the best-matching line (lyrics) or a window around the first hit (blurbs)
      var lines = String(text).split("\n"), bestL = "", bestS = -1;
      lines.forEach(function (l) {
        var n = norm(l), s = 0;
        toks.forEach(function (t) { if (n.indexOf(t) > -1) s++; });
        if (qn && n.indexOf(qn) > -1) s += toks.length;
        if (s > bestS) { bestS = s; bestL = l; }
      });
      if (bestL.length > 140) {
        var low = bestL.toLowerCase(), at = Math.max(0, low.indexOf(toks[0]) - 50);
        bestL = (at > 0 ? "…" : "") + bestL.slice(at, at + 130) + (at + 130 < bestL.length ? "…" : "");
      }
      return bestL;
    };
    var thumb = function (r) { return r && r.art ? '<img src="' + esc(sRoot + r.art) + '" alt="" width="44" height="44" loading="lazy" decoding="async">' : '<span class="sr-ph" aria-hidden="true"></span>'; };
    var CAP = { R: 6, T: 12, P: 5 };
    var run = function () {
      var q = sIn.value, qn = norm(q);
      if (qn === lastQ) return; lastQ = qn;
      if (!idx) return;
      if (!qn) { sOut.innerHTML = ""; sStat.textContent = ""; sIn.setAttribute("aria-expanded", "false"); return; }
      var toks = qn.split(" ").filter(function (t) { return t !== "or" && t !== "the" && t !== "a" || qn.split(" ").length === 1; });
      if (!toks.length) toks = qn.split(" ");
      fz = toks.map(function (t) { return idx.all.indexOf(t) < 0; });
      var html = "", count = 0;
      [["R", "Releases"], ["T", "Tracks"], ["P", "Pages"]].forEach(function (g) {
        var hits = [];
        idx[g[0]].forEach(function (o) { var s = score(o, toks, qn); if (s) hits.push({ o: o, s: s.s, f: s.field }); });
        if (!hits.length) return;
        hits.sort(function (a, b) { return b.s - a.s; });
        count += hits.length;
        var shown = hits.slice(0, CAP[g[0]]);
        html += '<section class="sr-g" aria-label="' + g[1] + '"><h3 class="sr-h">' + g[1] + '<span>' + (hits.length > shown.length ? shown.length + " of " + hits.length : hits.length) + "</span></h3><ul>";
        shown.forEach(function (h) {
          var o = h.o, href, art, title, meta, snip = "";
          if (g[0] === "R") {
            href = sRoot + "release/" + o.slug + "/"; art = thumb(o); title = o.title;
            meta = [o.type, o.genre, o.year].concat(o.instr ? ["Instrumental"] : []).join(" · ");
            if (h.f === 2) snip = snippet(o.blurb, toks, qn);
          } else if (g[0] === "T") {
            href = sRoot + "release/" + o.r.slug + "/#t" + o.n; art = thumb(o.r); title = o.title;
            meta = "Track " + o.n + " · " + o.r.title + (o.kind === "i" ? " · Instrumental" : "");
            if (h.f === 3) snip = "\u201C" + snippet(o.lyr, toks, qn) + "\u201D"; else if (h.f === 2) snip = snippet(o.blurb, toks, qn);
          } else {
            href = sRoot + o.path; art = '<span class="sr-ph sr-pg" aria-hidden="true"></span>'; title = o.title; meta = o.desc;
          }
          html += '<li><a class="sr-a" href="' + esc(href) + '">' + art + '<span class="sr-t"><span class="sr-tt">' + hl(title, toks) + '</span><span class="sr-m">' + hl(meta, toks) + "</span>"
            + (snip ? '<span class="sr-s">' + hl(snip, toks) + "</span>" : "") + "</span></a></li>";
        });
        html += "</ul></section>";
      });
      sOut.innerHTML = html || '<p class="sr-none">No matches for \u201C' + esc(q) + '\u201D. Try a song title, an album, a genre or a line from the lyrics.</p>';
      sStat.textContent = count ? count + " result" + (count === 1 ? "" : "s") : "No results";
      sIn.setAttribute("aria-expanded", count ? "true" : "false");
    };
    var load = function () {
      if (!idxP) idxP = fetch(sBtn.getAttribute("data-idx")).then(function (r) { if (!r.ok) throw r; return r.json(); })
        .then(function (d) { idx = prep(d); lastQ = null; run(); })
        .catch(function () { idxP = null; sStat.textContent = "Search couldn\u2019t load. Please try again."; });
      return idxP;
    };
    var build = function () {
      sDlg = document.createElement("dialog");
      sDlg.className = "search-dlg"; sDlg.setAttribute("aria-labelledby", "search-h");
      sDlg.innerHTML = '<div class="sd-box"><h2 class="sr-only" id="search-h">Search bfo.mantis</h2>'
        + '<div class="sd-bar">' + sBtn.querySelector("svg").outerHTML
        + '<input type="search" id="search-q" class="sd-in" placeholder="Search songs, albums, lyrics…" autocomplete="off" spellcheck="false" enterkeyhint="search" role="combobox" aria-expanded="false" aria-controls="search-out" aria-autocomplete="list" aria-describedby="search-stat" aria-label="Search songs, albums, lyrics and pages">'
        + '<button type="button" class="sd-close" aria-label="Close search"><span class="sd-esc" aria-hidden="true">Esc</span><svg class="sd-x" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg></button></div>'
        + '<p class="sr-only" id="search-stat" aria-live="polite"></p>'
        + '<div class="sd-out" id="search-out"></div>'
        + '<p class="sd-foot"><span><kbd>↑</kbd><kbd>↓</kbd> to move</span><span><kbd>Enter</kbd> to open</span><span><kbd>Esc</kbd> to close</span></p></div>';
      document.body.appendChild(sDlg);
      sIn = sDlg.querySelector(".sd-in"); sOut = sDlg.querySelector(".sd-out"); sStat = sDlg.querySelector("#search-stat");
      sIn.addEventListener("input", function () { clearTimeout(tmr); tmr = setTimeout(run, 90); });
      sDlg.querySelector(".sd-close").addEventListener("click", function () { sDlg.close(); });
      sDlg.addEventListener("click", function (ev) { if (ev.target === sDlg) sDlg.close(); });   // backdrop
      sDlg.addEventListener("close", function () { document.documentElement.classList.remove("search-open"); sBtn.focus(); });
      sOut.addEventListener("click", function (ev) {
        var a = ev.target.closest && ev.target.closest("a.sr-a"); if (!a) return;
        track("event/search/" + (a.closest(".sr-g").getAttribute("aria-label") || "").toLowerCase());
        var u = new URL(a.href, location.href);
        if (u.pathname === location.pathname && u.hash) { ev.preventDefault(); sDlg.close(); if (location.hash === u.hash) openTrack(); else location.hash = u.hash; }
        else sDlg.close();
      });
      sDlg.addEventListener("keydown", function (ev) {
        // Esc always closes (a search field would otherwise just clear itself); don't also stop the preview
        if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); sDlg.close(); return; }
        var links = Array.prototype.slice.call(sDlg.querySelectorAll("a.sr-a"));
        if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
          if (!links.length) return;
          ev.preventDefault();
          var i = links.indexOf(document.activeElement), next = ev.key === "ArrowDown" ? i + 1 : i - 1;
          if (next < 0) sIn.focus(); else links[Math.min(next, links.length - 1)].focus();
        } else if (ev.key === "Enter" && document.activeElement === sIn && links.length) { ev.preventDefault(); links[0].click(); }
        else if (ev.key === "Tab") {   // focus trap, in reading order: field, results, close
          var f = [sIn].concat(links, [sDlg.querySelector(".sd-close")]);
          var at = f.indexOf(document.activeElement);
          ev.preventDefault();
          f[(at + (ev.shiftKey ? -1 : 1) + f.length) % f.length].focus();
        }
      });
    };
    var openSearch = function () {
      if (!sDlg) build();
      if (sDlg.open) { sIn.focus(); return; }
      if (navBar && navBar.classList.contains("nav-open")) { navBar.classList.remove("nav-open"); if (tog) tog.setAttribute("aria-expanded", "false"); }
      document.documentElement.classList.add("search-open");
      sDlg.showModal(); sIn.focus(); sIn.select();
      if (!idx) { sStat.textContent = "Loading search…"; load(); }
    };
    sBtn.addEventListener("click", openSearch);
    on(document, "keydown", function (ev) {
      var t = ev.target, typing = t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
      if ((ev.key === "k" || ev.key === "K") && (ev.metaKey || ev.ctrlKey) && !ev.altKey) { ev.preventDefault(); openSearch(); }
      else if (ev.key === "/" && !typing && !ev.metaKey && !ev.ctrlKey && !ev.altKey && !document.querySelector("dialog[open]")) { ev.preventDefault(); openSearch(); }
    });
  }
  };
  init();

  // ---------- client-side navigation (only while the mini-player has a clip loaded) ----------
  // With nothing loaded, links are ordinary page loads. While a preview is loaded, same-site page links are fetched and
  // swapped in place so the clip keeps playing: the URL, history (back/forward), scroll position, <title>, meta tags
  // and the GoatCounter pageview all follow the new page. Any failure falls back to a normal page load.
  var canSPA = sigOK && !!(window.history && history.pushState && window.fetch && window.DOMParser && window.URL);
  if (canSPA) {
    var spaUsed = false, navSeq = 0, shownPath = location.pathname + location.search, sTick = 0;
    var saveScroll = function () {
      try { history.replaceState({ spa: 1, y: window.pageYOffset }, "", location.href); } catch (err) { /* ignore */ }
    };
    window.addEventListener("scroll", function () {
      if (!spaUsed) return;
      clearTimeout(sTick); sTick = setTimeout(saveScroll, 150);
    }, { passive: true });
    var HEAD_SEL = 'meta[name="description"], link[rel="canonical"], meta[property^="og:"], meta[name^="twitter:"], script[type="application/ld+json"], meta[name="robots"]';
    var swap = function (doc) {
      document.title = doc.title;
      each(HEAD_SEL, function (n) { n.parentNode.removeChild(n); }, document.head);
      each(HEAD_SEL, function (n) { document.head.appendChild(document.importNode(n, true)); }, doc.head);
      each("script", function (s) { if (s.type !== "application/ld+json") s.parentNode.removeChild(s); }, doc.body);
      var b = document.body;
      Array.prototype.slice.call(b.attributes).forEach(function (at) { b.removeAttribute(at.name); });
      Array.prototype.forEach.call(doc.body.attributes, function (at) { b.setAttribute(at.name, at.value); });
      Array.prototype.slice.call(b.childNodes).forEach(function (n) { if (n !== PL.mini) b.removeChild(n); });
      var frag = document.createDocumentFragment();
      Array.prototype.slice.call(doc.body.childNodes).forEach(function (n) { frag.appendChild(document.importNode(n, true)); });
      b.insertBefore(frag, PL.mini && PL.mini.parentNode === b ? PL.mini : null);
    };
    var go = function (url, push, st) {
      var my = ++navSeq, hash = url.indexOf("#") > -1 ? url.slice(url.indexOf("#")) : "";
      document.documentElement.classList.add("spa-loading");
      fetch(url, { credentials: "same-origin" }).then(function (r) {
        if (!r.ok || !/text\/html/.test(r.headers.get("content-type") || "")) throw new Error("not a page");
        return r.text().then(function (t) { return { t: t, u: r.url || url }; });
      }).then(function (res) {
        if (my !== navSeq) return;
        var doc = new DOMParser().parseFromString(res.t, "text/html");
        if (!doc.body || !doc.getElementById("main")) throw new Error("unexpected page");
        if (!spaUsed) { spaUsed = true; if ("scrollRestoration" in history) history.scrollRestoration = "manual"; }
        if (push) { saveScroll(); history.pushState({ spa: 1, y: 0 }, "", res.u.split("#")[0] + hash); }
        if (pageAC) pageAC.abort();
        swap(doc);
        shownPath = location.pathname + location.search;
        init();
        var y = !push && st && typeof st.y === "number" ? st.y : 0;
        var target = hash && hash.length > 1 && document.getElementById(decodeURIComponent(hash.slice(1)));
        if (target && !/^#t\d+$/.test(hash)) target.scrollIntoView(); else if (!/^#t\d+$/.test(hash)) window.scrollTo(0, y);
        var h = document.querySelector("#main h1") || document.getElementById("main");
        if (h && push) { if (!h.hasAttribute("tabindex")) h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
        try {   // pageview for the new page (GoatCounter only counts the first load by itself)
          var gc = window.goatcounter;
          if (gc && typeof gc.count === "function") gc.count({ path: location.pathname + location.search, title: document.title });
        } catch (err) { /* ignore */ }
      }).catch(function () {
        if (my !== navSeq) return;
        if (push) location.href = url; else location.reload();
      }).then(function () { if (my === navSeq) document.documentElement.classList.remove("spa-loading"); });
    };
    document.addEventListener("click", function (ev) {
      if (ev.defaultPrevented || ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
      if (!PL.active()) return;
      var a = ev.target.closest && ev.target.closest("a[href]");
      if (!a || (a.target && a.target !== "_self") || a.hasAttribute("download") || a.hasAttribute("data-no-spa")) return;
      var u; try { u = new URL(a.href, location.href); } catch (err) { return; }
      if (u.origin !== location.origin || !/(\/|\.html)$/.test(u.pathname)) return;   // other sites, files, feeds, PDFs
      if (u.pathname + u.search === location.pathname + location.search) return;   // same page (incl. #anchors)
      ev.preventDefault();
      go(u.href, true);
    });
    window.addEventListener("popstate", function (ev) {
      if (!spaUsed) return;
      if (location.pathname + location.search === shownPath) return;   // hash-only change
      go(location.href, false, ev.state);
    });
  }
})();
