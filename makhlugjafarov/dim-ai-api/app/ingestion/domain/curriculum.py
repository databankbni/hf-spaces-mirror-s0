"""Build a book's curriculum tree from its table of contents (GRO-156).

The table of contents (Mündəricat) is the one clean, complete, *named* topic map
every DİM textbook ships — and it encodes hierarchy the body OCR throws away:
chapters (``Fəsil`` / roman numerals / leading-digit ALL-CAPS banners), optional
mid-level sections (``Bölmə N``), and the numbered topics (``Mövzu``) under them.

``toc_anchor.extract_toc_anchors`` already mines the *topic* rows as flat
segmentation cut points. This module reads the **same** TOC pages but keeps the
hierarchy: it classifies each line as a chapter / section / topic, threads the
chapter and section banners (which carry no page number of their own) onto the
page of the first topic beneath them, and nests everything into
``CurriculumNode`` records keyed by ``node_path``.

It is best-effort and side-effect free: any book whose TOC does not parse yields
``[]`` and the pipeline degrades to a flat section list (GRO-91 contract).
Heavy compute never happens here — this is a light pass over already-OCR'd text.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.ingestion.domain.models import CurriculumNode, ParsedDocument
from app.ingestion.domain.toc_anchor import TOC_ROW_PATTERN, _toc_pages
from app.platform.text_quality import sanitize_section_title

logger = logging.getLogger(__name__)

# Rank = depth signal. Lower binds higher in the tree. A numberless ALL-CAPS
# *unit* banner (geo ``YERİN TƏBİƏTİ``) outranks a numbered/roman *chapter*,
# which outranks a ``Bölmə`` section, which outranks a numbered topic. These are
# *relative* ranks, not final levels: the stack collapses unused ranks, so a book
# with only chapters + topics still yields a clean depth-2 tree (no empty middle
# level), while one with all four tiers (geo) nests unit → chapter → topic.
_RANK_UNIT = 0
_RANK_CHAPTER = 1
_RANK_SECTION = 2
_RANK_TOPIC = 3

# Ranks an OCR-wrapped ALL-CAPS heading can split across. A ``Bölmə`` (SECTION)
# carries its own title and page and is never a wrap fragment, so it is excluded.
_BANNER_RANKS = frozenset({_RANK_UNIT, _RANK_CHAPTER})

_MAX_LEVEL = 6

# ``\section*{1. Funksiyalar}`` — the GOT-OCR math TOC wraps chapter banners in
# LaTeX section markup.
_LATEX_SECTION = re.compile(r"\\section\*?\{(.+?)\}")

# ``Bölmə 3. Epidemiologiya`` — the biology mid-level between unit and topic.
_SECTION_BOLME = re.compile(r"(?i)^\s*bölmə\s+\d+")

# TOC-structural words (the contents page's own heading + running cover echoes).
# These OCR onto the TOC page as ALL-CAPS lines and would otherwise be mistaken
# for chapter banners; they are never real curriculum nodes.
_STRUCTURAL = re.compile(r"(?i)mündəricat|içindəkilər|kitabin")

# ``II. Canlılarda ...`` / ``I. Yer ...`` — roman-numeral chapter prefix. OCR
# routinely renders ``II`` as ``ll`` or ``Il`` and ``III`` as ``lll``, so accept
# the look-alikes; a trailing ``.`` or ``)`` separator is required to avoid
# eating an ``I``-initial word.
_ROMAN_CHAPTER = re.compile(r"^\s*(?:[IVXLCDM]+|[lI]{2,})[.)]\s+\S")

# ``Fəsil`` / ``fəsil`` anywhere as a standalone word (``| fəsil``, ``II fəsil``,
# ``2-ci fəsil``). The literal keyword is the most reliable chapter signal where
# it appears (fizika).
_FESIL = re.compile(r"(?i)(?:^|\s)fəsil(?:\s|$)")

# ``1 AZƏRBAYCAN XVI ƏSRİN ...`` — a leading number then an ALL-CAPS banner with
# no dot-leader and no trailing page number (tarix chapter headers).
_NUMBERED_CAPS = re.compile(r"^\s*\d+\s+([A-ZÇƏĞİıÖŞÜ][A-ZÇƏĞİıÖŞÜ \-—,'’0-9]{6,})\s*$")

# Azerbaijani upper/lower sets for the bare-ALL-CAPS chapter test.
_AZ_UPPER = set("ABCÇDEƏFGĞHXIİJKQLMNOÖPRSŞTUÜVYZW")
_AZ_LOWER = set("abcçdeəfgğhxıijkqlmnoöprsştuüvyzw")

# ``Topic 42`` — a topic row whose page is separated by spaces, not a dot leader.
# Some TOCs (kimya) list most topics without leaders, so the dot-leader-only
# ``TOC_ROW_PATTERN`` drops half of them. Tested *after* every banner/leader rule,
# so a banner that carries a page (literature) and a real dotted row both win first.
_SPACED_TOPIC = re.compile(r"^(.+?\S)\s+(\d{1,4})\s*$")

# A leading chapter enumerator (``1 Alkanlar``, ``IV Alkinlər``) — arabic or roman,
# optional ``.``/``)``, then a space. Stripped only to *count* a page-less heading's
# words, so a numbered Title-case chapter is judged on its title, not its number.
_LEADING_ENUM = re.compile(r"^\s*(?:\d{1,3}|[IVXLCDMivxlcdm]{1,4})[.)]?\s+")


def _is_pageless_heading(line: str) -> bool:
    """A short, page-less, heading-shaped line is a chapter — even Title-case.

    The ALL-CAPS test (:func:`_is_caps_banner`) misses books that list chapters in
    Title case (kimya's carbon classes: ``Alkenlər``, ``Aromatik karbohidrogenlər``).
    The general chapter signal those share with every book is structural, not case:
    a chapter row carries **no page number** (its topics do) and is **terse**. The
    word cap is the guard against a *wrapped topic title* — a long fragment that also
    lost its page (``...qrafik formulları və molekullarının``) — being read as a
    chapter; a real chapter title is a few words, a wrap fragment is many.
    """
    if _trailing_page(line) is not None:
        return False  # has a page → it is a topic, not a chapter banner
    if re.match(r"^\s*\d+[.)]", line):
        return False  # ``28.`` — a numbered topic that lost its page to a wrap,
        # not a chapter. Kimya chapters are ``1 Alkanlar`` (digit + space, no dot).
    text = _LEADING_ENUM.sub("", line).strip(" .—-")
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 3 or text.endswith(","):
        return False
    if not 1 <= len(text.split()) <= 4:
        return False
    return text[:1] == text[:1].upper()  # heading-like: starts uppercase


def extract_curriculum_nodes(document: ParsedDocument) -> list[CurriculumNode]:
    """Parse the TOC into a nested ``CurriculumNode`` tree (document order).

    Returns ``[]`` on no parseable TOC or any error so a malformed contents page
    can never fail ingestion.
    """
    try:
        page_count = max((p.page_number for p in document.pages), default=0)
        offset = document.source.page_offset
        last_printed = page_count - offset if page_count else 0

        entries = _parse_entries(document)
        if not entries:
            return []
        _resolve_provisional_chapters(entries)
        _drop_implausible_pages(entries, last_printed=last_printed)
        _fill_parent_pages(entries)
        _merge_wrapped_banners(entries)
        entries = [e for e in entries if e.page is not None]
        if not entries:
            return []
        nodes = _build_tree(entries, last_printed=last_printed)
        return _prune_cover_echoes(nodes)
    except Exception as exc:  # never fail ingestion on a TOC parse error
        logger.warning(
            "Curriculum tree extraction failed for %s: %s",
            document.source.source_id,
            exc,
            exc_info=True,
        )
        return []


# Metadata key under which a section/chunk records the curriculum node it falls
# in. The loader resolves this path → the node's row id to set the FK; keeping it
# a path (not a uuid) keeps segmentation pure and DB-free.
CURRICULUM_NODE_PATH_KEY = "curriculum_node_path"

# Metadata key for the node's breadcrumb (root → leaf titles). Materialised at
# segmentation time so it rides through ``chunk.metadata`` into retrieval with no
# extra query — the same channel ``section_path_titles`` already uses.
CURRICULUM_PATH_TITLES_KEY = "curriculum_path_titles"


def node_title_path(nodes: list[CurriculumNode], node: CurriculumNode) -> list[str]:
    """The clean TOC titles from the root down to *node* (inclusive).

    Walks ``parent_path`` up the tree; cycle-guarded so a malformed path can't
    loop. Used to materialise a chunk's breadcrumb at ingestion time.
    """
    by_path = {n.node_path: n for n in nodes}
    titles: list[str] = []
    current: CurriculumNode | None = node
    seen: set[str] = set()
    while current is not None and current.node_path not in seen:
        titles.append(current.title)
        seen.add(current.node_path)
        current = by_path.get(current.parent_path) if current.parent_path else None
    return list(reversed(titles))


def resolve_node_for_page(
    nodes: list[CurriculumNode], printed_page: int | None
) -> CurriculumNode | None:
    """The deepest curriculum node whose page span contains *printed_page*.

    Spans are containment intervals (a parent covers its whole subtree), so the
    deepest match is the most specific topic on that page. Returns ``None`` when
    no node covers the page (e.g. front matter before the first chapter).
    """
    if printed_page is None:
        return None
    best: CurriculumNode | None = None
    for node in nodes:
        if node.page_start is None or node.page_end is None:
            continue
        if node.page_start <= printed_page <= node.page_end:
            if best is None or node.level > best.level:
                best = node
    return best


@dataclass
class _Entry:
    rank: int
    raw_title: str
    page: int | None  # printed page; None for a banner until threaded to a child
    # A Title-case page-less heading is a *provisional* chapter: confirmed only if
    # it heads a real topic. A wrapped topic's first line looks identical, so it is
    # validated by lookahead (:func:`_resolve_provisional_chapters`) before nesting.
    provisional: bool = False


def _resolve_provisional_chapters(entries: list[_Entry]) -> None:
    """Confirm or drop the Title-case page-less chapters from :func:`_is_pageless_heading`.

    A real chapter heads a topic whose title starts with a capital (``Alkenlər`` →
    ``Alkenlərin …``). A *wrapped topic*'s first line (``Vahid çevrə və triqonometrik``
    → ``funksiyalar``) looks the same but its continuation starts lowercase — it is
    the tail of one title, not a new chapter. Dropping the provisional chapter in that
    case leaves the tail as an ordinary topic (the pre-existing behaviour), so a narrow
    column TOC (math) is not shredded into false chapters while kimya still nests.
    """
    kept: list[_Entry] = []
    for i, entry in enumerate(entries):
        if entry.provisional:
            nxt = entries[i + 1] if i + 1 < len(entries) else None
            tail_first = next((c for c in nxt.raw_title if c.isalpha()), "") if nxt else ""
            if nxt is not None and nxt.rank == _RANK_TOPIC and tail_first.islower():
                continue  # wrapped-topic first line, not a chapter
            entry.provisional = False
        kept.append(entry)
    entries[:] = kept


def _parse_entries(document: ParsedDocument) -> list[_Entry]:
    """Classify every TOC line into a chapter / section / topic entry, in order."""
    entries: list[_Entry] = []
    for page in _toc_pages(document):
        for line in (page.text or "").split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            entry = _classify(stripped)
            if entry is not None:
                entries.append(entry)
    return entries


def _classify(line: str) -> _Entry | None:
    """Turn one TOC line into an entry, or ``None`` if it is not a TOC row.

    Chapter/section banners are tested before topic rows: a banner that happens
    to carry a trailing page number (literature: ``ERKƏN YENİ DÖVR ... 91``) must
    not be misread as a leaf topic.
    """
    latex = _LATEX_SECTION.search(line)
    if latex:
        return _Entry(_RANK_CHAPTER, latex.group(1).strip(), _trailing_page(line))

    if _STRUCTURAL.search(line):
        return None  # contents-page heading / cover echo, not a curriculum node

    if _SECTION_BOLME.match(line):
        return _Entry(_RANK_SECTION, _strip_leader(line), _trailing_page(line))

    if _FESIL.search(line):
        # A bare "Fəsil" marker (``| fəsil``, ``Il fəsil``) carries no title of
        # its own — the chapter's real title is the ALL-CAPS banner on the next
        # line, which we capture there. Only keep a Fəsil line that *is* the
        # title (``Fəsil 1. Mexanika``).
        if _is_bare_fesil_marker(line):
            return None
        return _Entry(_RANK_CHAPTER, _strip_leader(line), _trailing_page(line))

    if _ROMAN_CHAPTER.match(line) or _NUMBERED_CAPS.match(line):
        return _Entry(_RANK_CHAPTER, _strip_leader(line), _trailing_page(line))

    if _is_caps_banner(line):
        # A numberless ALL-CAPS banner is a unit/part heading sitting *above* the
        # numbered chapters it introduces (geo). Books without such banners simply
        # never emit a unit, and their chapters stay at the top level.
        return _Entry(_RANK_UNIT, _strip_leader(line), _trailing_page(line))

    if _is_pageless_heading(line):
        # A terse, page-less Title-case heading (kimya carbon classes) is a chapter
        # over the dotted topic rows that follow it. Provisional: a wrapped topic's
        # first line is indistinguishable here, so it is confirmed by lookahead.
        return _Entry(_RANK_CHAPTER, _strip_leader(line), None, provisional=True)

    row = TOC_ROW_PATTERN.match(line)
    if row:
        title = _clean_toc_title(row.group(1))
        try:
            page = int(row.group(2))
        except ValueError:
            return None
        if title and page >= 1:
            return _Entry(_RANK_TOPIC, title, page)

    spaced = _SPACED_TOPIC.match(line)
    if spaced:
        title = _clean_toc_title(spaced.group(1))
        page = int(spaced.group(2))
        if sum(c.isalpha() for c in title) >= 3 and page >= 1:
            return _Entry(_RANK_TOPIC, title, page)
    return None


# A TOC dot leader connects a title to its page number ("Topic .... 42"). OCR
# routinely garbles the page into the leader's tail ("...ə-3əə...8"), and
# ``TOC_ROW_PATTERN`` anchors on the *final* dot-run, leaving the leader + garble
# inside the captured title. Cutting at the first leader (3+ dots, spaced or not)
# drops the leader and everything after it — the page ref and its OCR noise.
_TOC_DOT_LEADER = re.compile(r"\.{3,}|(?:\.\s){2,}")


def _clean_toc_title(raw: str) -> str:
    """Strip a topic row's trailing dot leader and page-ref garble.

    Keeps only the text before the first dot leader, then removes any leftover
    trailing page number. A title with no leader is returned unchanged.
    """
    text = _TOC_DOT_LEADER.split(raw, maxsplit=1)[0]
    # Drop a trailing page ref, including OCR forms where the dot leader collapsed
    # into the number ("yaradıcılıq yolu 0.00", "… . 2") — a trailing run of
    # digits/dots/spaces after a space is never part of a real topic title.
    text = re.sub(r"\s+\d[\d.\s]*$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .—-")


def _is_bare_fesil_marker(line: str) -> bool:
    """True when a ``fəsil`` line is just the marker, with no real chapter title.

    Strips the ``fəsil`` keyword, roman/pipe/arabic chapter numerals and
    punctuation; if fewer than 3 letters remain it is a bare marker.
    """
    residual = re.sub(r"(?i)fəsil", "", line)
    residual = re.sub(r"[IVXLCDMlI|0-9.\-—:;,()\[\]]", "", residual)
    return sum(1 for c in residual if c.isalpha()) < 3


def _is_caps_banner(line: str) -> bool:
    """A bare ALL-CAPS heading line (geo ``YERİN TƏBİƏTİ``), no number prefix.

    Requires a run of mostly-uppercase letters so a Title-Case topic row that
    lost its dot-leader is not swept up as a chapter.
    """
    text = _strip_leader(line)
    letters = [c for c in text if c in _AZ_UPPER or c in _AZ_LOWER]
    if len(letters) < 6:
        return False
    upper = sum(1 for c in letters if c in _AZ_UPPER)
    words = text.split()
    # A real unit/part banner is multi-word ("YERİN TƏBİƏTİ"). A lone ALL-CAPS
    # token is a cover/running-header echo ("TARİXİ") — reject it so it can never
    # adopt the chapters that follow it.
    return upper / len(letters) >= 0.85 and 2 <= len(words) <= 9


def _trailing_page(line: str) -> int | None:
    match = re.search(r"(\d{1,4})\s*$", line.strip())
    if not match:
        return None
    try:
        page = int(match.group(1))
    except ValueError:
        return None
    return page if page >= 1 else None


def _strip_leader(line: str) -> str:
    """Drop a dot-leader + trailing page number, leaving the banner title."""
    text = re.sub(r"(?:\.{2,}|(?:\.\s){2,})\s*\d*\s*$", "", line).strip()
    text = re.sub(r"\s+\d{1,4}$", "", text).strip()
    return text.strip(" .")


def _drop_implausible_pages(entries: list[_Entry], *, last_printed: int) -> None:
    """Null out page numbers OCR mangled past the book's last page.

    A dot-leader row can OCR a stray digit into the page number (``... 0...`` →
    ``1603`` in a 212-page book). Such a page can't be a real anchor; dropping it
    lets the banner thread onto the next clean page instead of inventing a span.
    """
    if last_printed <= 0:
        return
    ceiling = last_printed + 2  # small slack for off-by-one printed/index drift
    for entry in entries:
        if entry.page is not None and entry.page > ceiling:
            entry.page = None


def _prune_cover_echoes(nodes: list[CurriculumNode]) -> list[CurriculumNode]:
    """Drop childless level-1 nodes that are a single ALL-CAPS token.

    The TOC page's OCR sweeps in cover/running-header fragments (``AZƏRBAYCAN``,
    ``TARİXİ``) as one-word ALL-CAPS banners. A real chapter title is never a
    lone word, so a childless single-token L1 is a cover echo, not a node.
    """
    has_children = {n.parent_path for n in nodes if n.parent_path}
    kept: list[CurriculumNode] = []
    for node in nodes:
        if (
            node.level == 1
            and node.node_path not in has_children
            and len(node.raw_title.split()) == 1
            and node.raw_title.isupper()
        ):
            continue
        kept.append(node)
    return _renumber_roots(kept)


def _renumber_roots(nodes: list[CurriculumNode]) -> list[CurriculumNode]:
    """Re-pack root ordinals/paths after a prune so node_path stays gap-free.

    Only roots are renumbered (and their descendants' path prefixes rewritten);
    a pruned cover echo is always a childless root, so no child loses its parent.
    """
    remap: dict[str, str] = {}
    next_root = 0
    for node in nodes:
        if node.parent_path is None:
            next_root += 1
            remap[node.node_path] = str(next_root)
    rebuilt: list[CurriculumNode] = []
    for node in nodes:
        old = node.node_path
        if node.parent_path is None:
            new_path = remap[old]
            new_parent = None
        else:
            new_parent = remap.get(node.parent_path, node.parent_path)
            new_path = f"{new_parent}.{node.ordinal}"
        remap[old] = new_path
        rebuilt.append(node.model_copy(update={"node_path": new_path, "parent_path": new_parent}))
    return rebuilt


def _fill_parent_pages(entries: list[_Entry]) -> None:
    """Thread each pageless banner onto the page of the next entry that has one.

    Chapter/section banners carry no page number in the TOC; their span starts
    where their first child does. Scanning forward to the next paged entry gives
    that start page.
    """
    next_page: int | None = None
    for entry in reversed(entries):
        if entry.page is not None:
            next_page = entry.page
        elif next_page is not None:
            entry.page = next_page


def _merge_wrapped_banners(entries: list[_Entry]) -> None:
    """Re-join an ALL-CAPS chapter banner that OCR split across two TOC lines.

    A long chapter heading — ``AZƏRBAYCAN XVIII ƏSRİN İKİNCİ YARISINDA`` — can
    wrap onto a second contents line. The continuation OCRs as its own ALL-CAPS
    banner with no number, threads (via ``_fill_parent_pages``) to the *same*
    start page as the head, and — being a same-or-shallower rank — would otherwise
    split off as a separate node and *adopt the head's topics*. That is exactly
    the History/Literature childless-top-level smell.

    The signature is general, not per-book: two consecutive banner entries (UNIT
    or CHAPTER) that thread to the **same page**, where the second is **no deeper**
    than the first, are one wrapped heading — a real child would be deeper, and a
    genuinely new same-rank chapter would start on its own page. A legitimate
    unit→chapter nesting (geography) is safe: there the second banner is *deeper*,
    so it is left alone. We concatenate the continuation onto the head and keep the
    head's rank (the head is the numbered/equal one, so its rank already wins).
    """
    merged: list[_Entry] = []
    for entry in entries:
        prev = merged[-1] if merged else None
        if (
            prev is not None
            and prev.rank in _BANNER_RANKS
            and entry.rank in _BANNER_RANKS
            and entry.rank <= prev.rank
            and entry.page is not None
            and entry.page == prev.page
        ):
            prev.raw_title = f"{prev.raw_title} {entry.raw_title}".strip()
            continue
        merged.append(entry)
    entries[:] = merged


def _build_tree(entries: list[_Entry], *, last_printed: int) -> list[CurriculumNode]:
    """Nest paged entries by rank into ``CurriculumNode`` records.

    A rank stack collapses unused middle ranks, so the emitted ``level`` is the
    node's real depth in *this* book's tree (1-based), not its absolute rank.
    """
    nodes: list[CurriculumNode] = []
    stack: list[CurriculumNode] = []  # current ancestor chain, shallow → deep
    child_counts: dict[str | None, int] = {}

    for entry in entries:
        while stack and stack[-1].metadata["_rank"] >= entry.rank:
            stack.pop()
        parent = stack[-1] if stack else None
        parent_path = parent.node_path if parent else None
        level = parent.level + 1 if parent else 1
        if level > _MAX_LEVEL:
            level = _MAX_LEVEL

        ordinal = child_counts.get(parent_path, 0) + 1
        child_counts[parent_path] = ordinal
        node_path = f"{parent_path}.{ordinal}" if parent_path else str(ordinal)

        clean = sanitize_section_title(entry.raw_title)
        node = CurriculumNode(
            node_path=node_path,
            parent_path=parent_path,
            level=level,
            ordinal=ordinal,
            title=clean or _basic_clean(entry.raw_title),
            raw_title=entry.raw_title,
            page_start=entry.page,
            extraction_method="toc",
            extraction_confidence=1.0 if clean else None,
            metadata={"_rank": entry.rank, "title_clean": clean is not None},
        )
        nodes.append(node)
        stack.append(node)

    _assign_page_ends(nodes, last_printed=last_printed)
    for node in nodes:
        node.metadata.pop("_rank", None)
    return nodes


def _assign_page_ends(nodes: list[CurriculumNode], *, last_printed: int) -> None:
    """Close each node's page span at the next same-or-shallower node's start.

    A parent then extends to cover its whole subtree (the last descendant's end),
    so ``[page_start, page_end]`` is a true containment interval the retrieval and
    module-read paths can range-query.
    """
    for i, node in enumerate(nodes):
        end = last_printed or node.page_start
        for later in nodes[i + 1 :]:
            if later.level <= node.level:
                end = (later.page_start or node.page_start or 1) - 1
                break
        node.page_end = max(end, node.page_start or 1)

    # Post-order: a parent spans to its deepest descendant.
    by_parent: dict[str | None, list[CurriculumNode]] = {}
    for node in nodes:
        by_parent.setdefault(node.parent_path, []).append(node)
    for node in reversed(nodes):
        children = by_parent.get(node.node_path)
        if children:
            node.page_end = max(c.page_end or 0 for c in children) or node.page_end


def _basic_clean(raw: str) -> str:
    """Minimal fallback label when the sanitizer rejects a title as garble.

    A node must carry a non-empty title (DB ``not null``); keep a trimmed raw so
    the structure survives even when the OCR'd banner is too noisy to fully
    clean. Such nodes are flagged ``title_clean=False`` for later repair.

    Runs the dot-leader cut as a safety net: this is the path garbled topic rows
    fall to (``sanitize_section_title`` rejects them), so it must never let a
    leader + page-ref tail through into the stored title.
    """
    text = _clean_toc_title(raw)
    text = re.sub(r"\s+", " ", text).strip(" .—-")
    return text or "(adsız)"
