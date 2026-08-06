"""HTML for the results list.

The list is plain markup with `data-` attributes; a single delegated click
handler in the page head turns any timestamp into a seek. No per-card
JavaScript, no component churn — Gradio only ever hands back a string.
"""

from __future__ import annotations

from html import escape

from search import MAX_SHOWN_EVENTS, Hit


def _safe_url(url: str | None) -> str:
    """Only ever emit an http(s) link. The URLs come from the dataset, and a
    link labelled 'archive.org' should not be able to send a visitor to a
    `javascript:` or `data:` target if a row is ever wrong."""
    url = (url or "").strip()
    return url if url.startswith(("https://", "http://")) else "#"


def clock(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


MIN_EVENTS = 3


def _events_html(hit: Hit) -> str:
    """Matched events, padded with their neighbours up to a readable minimum.

    A semantic hit often matches no event text literally — the query never
    appears in the captions — so without padding those results collapse to one
    line. Padding is greyed: only literal matches get the accent, which keeps
    the colour honest about what it means.
    """
    matched = hit.matched[:MAX_SHOWN_EVENTS]
    hits = {id(e) for e in matched}
    shown = list(matched)
    for event in hit.events:
        if len(shown) >= MIN_EVENTS:
            break
        if id(event) not in hits:
            shown.append(event)
    shown.sort(key=lambda e: e["start"])
    if not shown:
        return ""
    rows = []
    for event in shown:
        rows.append(
            "<li{cls}>"
            '<button class="at" data-src="{src}" data-t="{t}" '
            'data-title="{title}" data-when="{when}">{when}</button>'
            "<span>{text}</span>"
            "</li>".format(
                cls=' class="hit"' if id(event) in hits else "",
                src=escape(hit.video_url, quote=True),
                t=f"{event['start']:.2f}",
                title=escape(hit.title, quote=True),
                when=clock(event["start"]),
                text=escape(event["text"]),
            )
        )
    return f'<ul class="events">{"".join(rows)}</ul>'


def moment(hit: Hit) -> str:
    when = clock(hit.jump)
    stamp = " · ".join(
        part
        for part in (
            str(hit.year) if hit.year else "undated",
            f"{clock(hit.chunk_start)}–{clock(hit.chunk_end)}",
        )
        if part
    )
    scene = escape(hit.scene)
    scene_html = (
        f'<details class="scene"><summary>scene</summary><p>{scene}</p></details>'
        if scene
        else ""
    )
    return f"""
<article class="moment" id="m-{escape(hit.moment_id, quote=True)}">
  <button class="frame" data-src="{escape(hit.video_url, quote=True)}"
          data-t="{hit.jump:.2f}" data-title="{escape(hit.title, quote=True)}"
          data-when="{when}" aria-label="Play {escape(hit.title, quote=True)} at {when}">
    <img src="{escape(hit.thumb_url, quote=True)}" alt="" loading="lazy" decoding="async">
    <span class="cue">{when}</span>
  </button>
  <div class="meta">
    <h2>{escape(hit.title)}</h2>
    <p class="stamp">{stamp}
      <a href="{escape(_safe_url(hit.ia_url), quote=True)}" target="_blank" rel="noopener">archive.org</a>
    </p>
    {_events_html(hit)}
    {scene_html}
  </div>
</article>
"""


def opening(hits: list[Hit]) -> str:
    """What an empty search box shows: some of the collection, not a blank page.

    Every tile plays, so the first thing the page offers is the thing it does.
    """
    if not hits:
        return ""
    tiles = []
    for hit in hits:
        when = clock(hit.chunk_start)
        tiles.append(
            f"""
<div class="tile">
  <button class="frame" data-src="{escape(hit.video_url, quote=True)}"
          data-t="{hit.chunk_start:.2f}" data-title="{escape(hit.title, quote=True)}"
          data-when="{when}" aria-label="Play {escape(hit.title, quote=True)} at {when}">
    <img src="{escape(hit.thumb_url, quote=True)}" alt="" loading="lazy" decoding="async">
    <span class="cue">{when}</span>
  </button>
  <h3>{escape(hit.title)}</h3>
  <p class="stamp">{hit.year or "undated"}</p>
  <!-- Not shown in the grid, but the player panel clones it on click: browsing
       at random should show you what the model wrote, not just play the clip. -->
  <div class="detail" hidden>
    {_events_html(hit)}
    <div class="scene"><p>{escape(hit.scene)}</p></div>
  </div>
</div>"""
        )
    return (
        '<p class="count">a few moments, at random — click one to read what the '
        "model saw</p>"
        f'<div class="opening">{"".join(tiles)}</div>'
    )


def results(hits: list[Hit], query: str, elapsed_ms: float) -> str:
    if not query.strip():
        return ""
    if not hits:
        return (
            '<p class="empty">Nothing for <em>%s</em>. '
            "The captions describe what is on screen — try what you would "
            "<em>see</em>: a place, an object, an action.</p>" % escape(query)
        )
    films = len({h.identifier for h in hits})
    head = (
        f'<p class="count">{len(hits)} moments · {films} '
        f'{"film" if films == 1 else "films"}'
        f'<span class="ms">{elapsed_ms:.0f} ms</span></p>'
    )
    return head + "".join(moment(h) for h in hits)
