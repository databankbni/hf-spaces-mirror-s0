// Search and playback. One delegated click listener for the whole page: any
// element carrying data-src/data-t is a seek.
(function () {
  var form = document.getElementById("search");
  var results = document.getElementById("results");
  var q = document.getElementById("q");

  function stage() { return document.getElementById("stage"); }
  function player() { return document.getElementById("player"); }

  // --- search -------------------------------------------------------------

  var inFlight = null;

  function params() {
    var p = new URLSearchParams();
    p.set("q", q ? q.value : "");
    var d = document.getElementById("decade");
    var s = document.getElementById("spread");
    var m = document.getElementById("mode");
    if (d) p.set("decade", d.value);
    if (s) p.set("spread", s.checked ? "1" : "0");
    if (m) p.set("mode", m.value);
    return p;
  }

  function run(push) {
    if (!results) return;
    var p = params();
    if (inFlight) inFlight.abort();
    inFlight = new AbortController();
    fetch("/api/search?" + p.toString(), { signal: inFlight.signal })
      .then(function (r) { return r.json(); })
      .then(function (data) { results.innerHTML = data.html; })
      .catch(function (e) { if (e.name !== "AbortError") console.error(e); });
    // Results become linkable, which a search tool should be.
    if (push !== false) {
      var qs = p.get("q") ? "?" + p.toString() : location.pathname;
      history.replaceState(null, "", qs);
    }
  }

  if (form) {
    form.addEventListener("submit", function (e) { e.preventDefault(); run(); });
    form.addEventListener("change", function (e) {
      if (e.target.id === "decade" || e.target.id === "spread" || e.target.id === "mode") run();
    });
  }
  document.addEventListener("click", function (e) {
    var chip = e.target.closest && e.target.closest(".chip");
    if (chip && q) { q.value = chip.textContent.trim(); run(); }
  });

  // Restore state from the URL so a shared link opens the same search.
  (function restore() {
    var p = new URLSearchParams(location.search);
    if (!p.get("q")) return;
    if (q) q.value = p.get("q");
    var d = document.getElementById("decade");
    var s = document.getElementById("spread");
    var m = document.getElementById("mode");
    if (d && p.get("decade")) d.value = p.get("decade");
    if (s && p.get("spread")) s.checked = p.get("spread") === "1";
    if (m && p.get("mode")) m.value = p.get("mode");
    run(false);
  })();

  // --- playback -----------------------------------------------------------

  // A bucket `resolve/` URL 302s to a per-request signed CDN URL. Safari's
  // follow-up range requests don't re-sign and come back 403 (206, then 403,
  // then MEDIA_ERR_SRC_NOT_SUPPORTED); Chrome re-follows and never notices.
  // Resolving the signed URL once and handing that to the element works in
  // both. Cached per film so repeat taps stay synchronous.
  var resolved = Object.create(null);
  var pending = Object.create(null);   // in-flight, so pointerdown+click share one fetch
  var token = 0;                       // monotonic; identifies the current selection

  function resolve(src) {
    if (resolved[src]) return Promise.resolve(resolved[src]);
    if (pending[src]) return pending[src];
    pending[src] = fetch(src).then(function (res) {
      try { res.body.cancel(); } catch (e) { /* already drained */ }
      resolved[src] = res.url || src;
      return resolved[src];
    }).catch(function () {
      return src;
    }).then(function (url) {
      delete pending[src];
      return url;
    });
    return pending[src];
  }

  function setPaused(v) {
    var s = stage();
    if (s) s.classList.toggle("paused", v.paused);
  }

  function seek(v, t) {
    try { v.currentTime = t; } catch (e) { /* metadata not in yet */ }
  }

  function load(v, url, t, src) {
    // An element left in error state rejects play() before it can be unlocked,
    // so a second tap would show a frame that never starts. Reset it first.
    if (v.error) { v.removeAttribute("src"); v.load(); }
    // #t= is a media fragment: the browser starts there itself, and being
    // client-side it never touches the URL's signature.
    v.src = url + "#t=" + t.toFixed(2);
    v.addEventListener("loadedmetadata", function once() {
      v.removeEventListener("loadedmetadata", once);
      if (Math.abs(v.currentTime - t) > 1) seek(v, t);
    });
    v.load();
    // Keyed by the bucket URL, not the signed one, because that is what the
    // markup and the resolve cache are keyed by.
    v.dataset.loadedSrc = src;
    // Try to play, because a tap is usually enough and one tap beats two. Never
    // force it: if the browser declines, the paused state shows a play control.
    // Resynchronise in both branches — waiting on a media event can leave the
    // control hidden over a paused player, which is the worst of both.
    v.play().then(function () { setPaused(v); }).catch(function () { setPaused(v); });
  }

  var opener = null;   // where focus should return when the panel closes

  function play(el) {
    var s = stage(), v = player();
    if (!s || !v) return;
    var src = el.getAttribute("data-src");
    var t = parseFloat(el.getAttribute("data-t")) || 0;
    // A tap on a cloned line inside the panel is a seek within what is already
    // playing — not a new selection. It must not rebuild the panel, because the
    // clone has no .moment ancestor and rebuilding would delete the very list
    // being tapped.
    var inPanel = !!el.closest("#stage-list");
    if (!inPanel) opener = el;

    s.hidden = false;
    document.body.classList.add("has-stage");

    if (!inPanel) {
      document.querySelectorAll(".moment.playing, .tile.playing").forEach(function (m) {
        m.classList.remove("playing");
      });
      // .tile too: opening moments carry a hidden .detail block so browsing
      // at random shows the description, not just the video.
      var card = el.closest(".moment, .tile");
      if (card) card.classList.add("playing");

      var meta = document.getElementById("stage-meta");
      if (meta) {
        meta.innerHTML = "<b></b><span class='cut'></span>" +
          "<button type='button' id='stage-close'>close</button>";
        meta.querySelector("b").textContent = el.getAttribute("data-title") || "";
        meta.querySelector(".cut").textContent = "at " + (el.getAttribute("data-when") || "");
      }

      // The panel carries the shot list of what is playing, cloned from the
      // result rather than re-sent: every line in it is a seek, because this
      // same handler matches data-src/data-t anywhere on the page.
      var list = document.getElementById("stage-list");
      if (list) {
        list.innerHTML = "";
        if (card) {
          var events = card.querySelector(".events");
          if (events) list.appendChild(events.cloneNode(true));
          var scene = card.querySelector(".scene p");
          if (scene) {
            var para = document.createElement("p");
            para.className = "scene-text";
            para.textContent = scene.textContent;
            list.appendChild(para);
          }
        }
      }
    } else {
      var cut = document.querySelector("#stage-meta .cut");
      if (cut) cut.textContent = "at " + (el.getAttribute("data-when") || "");
    }

    // `requestedSrc` is what the viewer asked for; `loadedSrc` is what the
    // element actually has. Conflating them meant a second tap during a slow
    // resolution seeked the *previous* film.
    var me = ++token;
    var loaded = v.dataset.loadedSrc === src;
    v.dataset.requestedSrc = src;
    v.dataset.wanted = String(t);
    setPaused(v);

    if (loaded) { seek(v, t); v.play().then(function () { setPaused(v); })
                               .catch(function () { setPaused(v); }); return; }
    // Switching films: stop the old one rather than letting it play on unseen
    // while the new URL resolves.
    if (v.dataset.loadedSrc && !v.paused) v.pause();
    if (resolved[src]) { load(v, resolved[src], t, src); return; }
    resolve(src).then(function (url) {
      if (me !== token) return;                       // superseded by another tap
      load(v, url, parseFloat(v.dataset.wanted) || t, src);
    });
  }

  // Autoplay rules differ per browser, platform, and prior engagement. Rather
  // than predict them, tell the truth: if it is paused, show a play control.
  ["play", "playing", "pause", "ended", "loadeddata", "emptied", "waiting"].forEach(function (evt) {
    document.addEventListener(evt, function (e) {
      var v = player();
      if (v && e.target === v) setPaused(v);
    }, true);
  });

  // A signed URL eventually expires. Drop it and try once more. Capture is
  // required: media `error` does not bubble.
  document.addEventListener("error", function (e) {
    var v = player();
    if (!v || e.target !== v) return;
    var src = v.dataset.requestedSrc;
    // Retry even when the first resolve fell back to the raw URL — that case
    // is exactly the one most likely to have failed.
    if (!src || v.dataset.retried === src) return;
    v.dataset.retried = src;
    delete resolved[src];
    var me = ++token;
    resolve(src).then(function (url) {
      if (me !== token) return;                       // a newer selection won
      load(v, url, parseFloat(v.dataset.wanted) || 0, src);
    });
  }, true);

  // One successful load re-arms the retry, so a signature expiring later in the
  // session can still recover.
  document.addEventListener("loadeddata", function (e) {
    var v = player();
    if (v && e.target === v) delete v.dataset.retried;
  }, true);

  // pointerdown fires before click, so the fetch is usually already done by the
  // time the tap completes, which keeps play() inside the gesture.
  document.addEventListener("pointerdown", function (e) {
    var el = e.target.closest && e.target.closest("[data-src][data-t]");
    if (el) resolve(el.getAttribute("data-src"));
  }, true);

  document.addEventListener("click", function (e) {
    var big = e.target.closest && e.target.closest("#stage-play");
    if (big) {
      var vp = player();
      vp.play().then(function () { setPaused(vp); }).catch(function () { setPaused(vp); });
      return;
    }

    if (e.target.closest && e.target.closest("#stage-close")) {
      var s = stage(), v = player();
      if (v) v.pause();
      if (s) s.hidden = true;
      document.body.classList.remove("has-stage");
      document.querySelectorAll(".moment.playing, .tile.playing").forEach(function (m) {
        m.classList.remove("playing");
      });
      // Don't strand focus on a button that just disappeared.
      if (opener && opener.isConnected) opener.focus();
      opener = null;
      return;
    }

    var el = e.target.closest && e.target.closest("[data-src][data-t]");
    if (el) { e.preventDefault(); play(el); }
  });
})();
