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
  var narrow = window.matchMedia ? matchMedia("(max-width: 780px)") : null;
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
  each("details.tmore", function (d) {
    d.addEventListener("toggle", function () {
      if (!d.open) return;
      var n = d.closest("li").querySelector(".n");
      track("event/blurb/" + relSlug(d) + "/" + ("0" + (n ? n.textContent.trim() : "")).slice(-2));
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
    // Mini-player: a bar fixed to the bottom of the viewport while a clip is loaded (title, cover, play/pause, progress,
    // close). Built on first play; the shared <audio> keeps playing while the page scrolls.
    var mini = null, miniPP, miniT, miniS, miniArt, miniTime, miniBar;
    var svgPlay = '<svg class="i-play" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z" fill="currentColor"/></svg>';
    var svgPause = '<svg class="i-pause" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor"/></svg>';
    var buildMini = function () {
      mini = document.createElement("div");
      mini.className = "mini"; mini.hidden = true;
      mini.setAttribute("role", "region"); mini.setAttribute("aria-label", "Preview player");
      mini.innerHTML = '<img class="mini-art" alt="" width="44" height="44"><div class="mini-meta"><span class="mini-t"></span><span class="mini-s"></span></div>' +
        '<span class="mini-time" aria-hidden="true">0:00 / 0:30</span>' +
        '<button type="button" class="mini-pp" aria-label="Pause preview">' + svgPlay + svgPause + '</button>' +
        '<button type="button" class="mini-x" aria-label="Close preview player"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg></button>' +
        '<span class="mini-prog" aria-hidden="true"><span></span></span>';
      document.body.appendChild(mini);
      miniPP = mini.querySelector(".mini-pp"); miniT = mini.querySelector(".mini-t"); miniS = mini.querySelector(".mini-s");
      miniArt = mini.querySelector(".mini-art"); miniTime = mini.querySelector(".mini-time"); miniBar = mini.querySelector(".mini-prog > span");
      miniPP.addEventListener("click", function () { if (current) play(current); });
      mini.querySelector(".mini-x").addEventListener("click", closeMini);
    };
    var showMini = function () {
      if (!current) return;
      if (!mini) buildMini();
      miniT.textContent = current.getAttribute("data-title") || "";
      var rel = current.getAttribute("data-rel") || "", href = current.getAttribute("data-href");
      miniS.textContent = "";
      if (rel && href && location.pathname.replace(/index\.html$/, "") !== new URL(href, location.href).pathname) {
        var a = document.createElement("a"); a.href = href; a.textContent = rel; miniS.appendChild(a);
      } else miniS.textContent = rel ? rel + " · 30s preview" : "30s preview";
      var art = current.getAttribute("data-art");
      if (art) { if (miniArt.getAttribute("src") !== art) miniArt.src = art; miniArt.hidden = false; } else miniArt.hidden = true;
      if (mini.hidden) { mini.hidden = false; body.classList.add("has-mini"); fabUpdate(); }
    };
    var closeMini = function () {
      audio.pause();
      var btn = current; setState(false); reset(btn); audio.currentTime = 0;
      if (timeEl) timeEl.textContent = "0:00 / 0:30";
      if (mini) { mini.hidden = true; body.classList.remove("has-mini"); }
      fabUpdate();
      if (btn && btn.offsetParent) btn.focus(); else if (top) top.focus();
    };
    var miniState = function (playing) {
      if (!mini || !current) return;
      miniPP.classList.toggle("is-playing", playing);
      miniPP.setAttribute("aria-label", (playing ? "Pause" : "Play") + " preview of " + current.getAttribute("data-title"));
    };
    var miniProgress = function () {
      if (!mini || mini.hidden) return;
      var d = audio.duration || 30;
      miniBar.style.transform = "scaleX(" + Math.min(1, (audio.currentTime || 0) / d) + ")";
      miniTime.textContent = mmss(audio.currentTime) + " / " + mmss(d);
    };

    // Phones: a floating "Play latest" / "Play preview" button once the page's main player has scrolled out of view
    // (hidden while the mini-player is open). The page gets matching bottom padding so nothing ends up underneath it.
    var fab = null, mainOut = false;
    var fabUpdate = function () {
      if (!fab) return;
      var on = mainOut && (!mini || mini.hidden) && narrow && narrow.matches;
      fab.classList.toggle("is-on", !!on);
      fab.tabIndex = on ? 0 : -1; fab.setAttribute("aria-hidden", on ? "false" : "true");
      body.classList.toggle("has-fab", !!on);
    };
    if (main) {
      fab = document.createElement("button");
      fab.type = "button"; fab.className = "fab-play"; fab.tabIndex = -1; fab.setAttribute("aria-hidden", "true");
      fab.innerHTML = svgPlay + "<span></span>";
      fab.querySelector("span").textContent = main.getAttribute("data-fab") || "Play preview";
      document.body.appendChild(fab);
      fab.addEventListener("click", function () { play(current || pvButtons[0]); });
      // the main player counts as "out of view" once it has scrolled above the viewport (rAF-throttled, read-only)
      var fabTick = false;
      var fabCheck = function () {
        fabTick = false;
        if (!narrow || !narrow.matches) { if (mainOut) { mainOut = false; fabUpdate(); } return; }
        var out = main.getBoundingClientRect().bottom < 72;   // i.e. behind or above the sticky header
        if (out !== mainOut) { mainOut = out; fabUpdate(); }
      };
      window.addEventListener("scroll", function () { if (!fabTick) { fabTick = true; requestAnimationFrame(fabCheck); } }, { passive: true });
      window.addEventListener("load", fabCheck);
      if (narrow && narrow.addEventListener) narrow.addEventListener("change", fabCheck);
    }

    audio.addEventListener("play", function () { setState(true); showMini(); miniState(true); });
    audio.addEventListener("pause", function () { setState(false); miniState(false); });
    audio.addEventListener("timeupdate", function () { progress(); miniProgress(); });
    audio.addEventListener("ended", function () {
      setState(false); miniState(false); reset(current); audio.currentTime = 0; if (timeEl) timeEl.textContent = "0:00 / 0:30";
      if (miniBar) miniBar.style.transform = "scaleX(0)";
    });
    audio.addEventListener("error", function () {
      if (!current) return;
      setState(false); miniState(false); if (nowEl) nowEl.textContent = "Preview unavailable";
    });
    document.addEventListener("keydown", function (ev) {   // Esc stops the preview (unless it is closing the lightbox)
      if (ev.key === "Escape" && !audio.paused && !document.querySelector("dialog[open]")) audio.pause();
    });
  }

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
    document.addEventListener("click", function (ev) { if (!g.contains(ev.target)) setG(false); });
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

  // Email sign-up (only live when email_signup_url is configured): count the submission.
  document.addEventListener("submit", function (ev) {
    var f = ev.target;
    if (f && f.hasAttribute && f.hasAttribute("data-gc")) track(f.getAttribute("data-gc"));
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
        ccp.textContent = "A room for fans of bfo.mantis in " + name + " to talk about their favorite songs.";
        if (top_) {
          ccp.appendChild(document.createTextNode(" bfo.mantis has listeners here. Most played: "));
          var ta = document.createElement("a"); ta.href = b.getAttribute("data-top-href"); ta.textContent = top_; ccp.appendChild(ta);
          ccp.appendChild(document.createTextNode("."));
        }
        if (join && join.tagName === "A") join.setAttribute("data-gc", "event/community/" + b.getAttribute("data-cc").toLowerCase());
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
  }
})();
