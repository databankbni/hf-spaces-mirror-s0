r"""
J.R. Kantor Research System — v3 "Explorer"
===========================================
What's new vs v2:
  - EXPLORATION MODE: the LLM explores the corpus in several rounds
    (semantic search + exact-phrase search + page context + term timeline)
    instead of answering from one fixed batch of 8 chunks.
  - Exact/full-text search (SQLite FTS5) built at startup from the same
    index_data.pkl — finds literal phrases, author names, rare terms.
  - Term timeline tool: counts a term's appearances per year/work,
    so "how did X evolve?" questions get real chronology.
  - Quick mode (the classic v2 single-pass pipeline) is still there.
  - Complete visual redesign: quiet academic typography, one restrained
    accent, no boxes-inside-boxes.

Stack: nomic-embed-text-v1.5 + FAISS + cross-encoder rerank (unchanged),
SQLite FTS5, Groq llama-3.3-70b-versatile with tool calling, Gradio.
"""

import gradio as gr
import os
import re
import json
import pickle
import sqlite3
import numpy as np

STUB_LLM = os.environ.get("KANTOR_STUB_LLM") == "1"  # local UI testing without models

if not STUB_LLM:
    import faiss
    from groq import Groq
    from sentence_transformers import SentenceTransformer, CrossEncoder

# ── Config ──────────────────────────────────────────────────────
DB_DIR = "./database"
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1.5"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
LLM_MODEL = "llama-3.3-70b-versatile"
MAX_ROUNDS = 6          # max tool-calling rounds in exploration mode

# ── Initialize ──────────────────────────────────────────────────
if not STUB_LLM:
    print("Loading embedding model...")
    model = SentenceTransformer(EMBEDDING_MODEL, trust_remote_code=True)
    print("Loading reranker model...")
    reranker = CrossEncoder(RERANKER_MODEL, max_length=512)
    print("Loading FAISS index...")
    index = faiss.read_index(os.path.join(DB_DIR, "index.faiss"))
else:
    model = reranker = index = None

print("Loading metadata...")
with open(os.path.join(DB_DIR, "index_data.pkl"), "rb") as f:
    data = pickle.load(f)
texts = data["texts"]
metadatas = data["metadatas"]
print(f"Metadata loaded: {len(texts)} chunks")

summary_path = os.path.join(DB_DIR, "index_summary.json")
if os.path.exists(summary_path):
    with open(summary_path) as f:
        index_summary = json.load(f)
else:
    index_summary = {"total_chunks": len(texts), "total_entries": "?", "types": {}}

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY")) if not STUB_LLM else None

# ── Full-text index (FTS5), built once at startup ───────────────
print("Building full-text index...")
fts = sqlite3.connect(":memory:", check_same_thread=False)
fts.execute("CREATE VIRTUAL TABLE chunks USING fts5(text, title, year, doc_type, start_page, end_page, cid)")
fts.executemany(
    "INSERT INTO chunks VALUES (?,?,?,?,?,?,?)",
    [(t, m.get("title", ""), str(m.get("year", "")), m.get("type", ""),
      str(m.get("start_page", "")), str(m.get("end_page", "")), str(i))
     for i, (t, m) in enumerate(zip(texts, metadatas))],
)
fts.commit()
import threading
fts_lock = threading.Lock()
print("System ready!")

# ── Shared helpers (unchanged from v2) ──────────────────────────
TYPE_LABELS = {"Book": "Book", "Article": "Article", "Review": "Book Review", "Observer": "Observer Column"}


def format_page_ref(meta):
    start, end = meta.get("start_page"), meta.get("end_page")
    if not start:
        return ""
    return f"p. {start}" if (start == end or not end) else f"pp. {start}–{end}"


def format_citation(meta):
    title = meta.get("title", "Unknown").strip()
    year = meta.get("year", "n.d.")
    label = TYPE_LABELS.get(meta.get("type", ""), meta.get("type", ""))
    citation = f"Kantor, J.R. ({year}). *{title}* [{label}]"
    page_ref = format_page_ref(meta)
    return citation + (f", {page_ref}" if page_ref else "")


def format_citation_short(meta):
    cite = f"Kantor ({meta.get('year', 'n.d.')}), \"{meta.get('title', 'Unknown').strip()}\""
    page_ref = format_page_ref(meta)
    return cite + (f", {page_ref}" if page_ref else "")


def is_valid_chunk(text):
    if not text or len(text.strip()) < 30:
        return False
    return len(re.sub(r"[^a-zA-Z]", "", text)) >= 20


def is_metadata_heavy(text, meta):
    t = text.lower()
    if "requests for reprints" in t:
        return True
    if meta.get("start_page", 0) == 1:
        signals = 0
        if "abstract" in t: signals += 2
        if "resumen" in t: signals += 2
        if "vol." in t or "vol " in t: signals += 1
        if "pp." in t or "pp " in t: signals += 1
        if "university" in t and "indiana" in t: signals += 1
        if "revista" in t or "journal" in t: signals += 1
        if signals >= 3:
            return True
    return False


def is_reference_list(text):
    if len(re.findall(r"Kantor,\s*J\.?\s*R\.?", text)) >= 3:
        return True
    if len(re.findall(r"\b1[89]\d{2},\s*\d+,\s*\d+", text)) >= 3:
        return True
    years = len(re.findall(r"\b1[89]\d{2}\b", text))
    return years >= 6 and years / max(len(text) / 100.0, 1.0) > 1.0


def word_quality(text):
    tokens = re.findall(r"[A-Za-z]+", text)
    if not tokens:
        return 0.0
    good = sum(1 for t in tokens if len(t) >= 2 and (t.islower() or t.istitle() or (t.isupper() and len(t) <= 4)))
    return good / len(tokens)


def junk(text, meta):
    return (not is_valid_chunk(text)) or is_reference_list(text) or is_metadata_heavy(text, meta) or word_quality(text) < 0.78


# ── Evidence registry ───────────────────────────────────────────
class Evidence:
    """Collects every passage the model saw, so citations map to real text."""

    def __init__(self):
        self.items = []          # list of dicts: cid, meta, text
        self.by_cid = {}

    def add(self, cid, text, meta):
        if cid in self.by_cid:
            return self.by_cid[cid]
        n = len(self.items) + 1
        self.items.append({"n": n, "cid": cid, "text": text, "meta": meta})
        self.by_cid[cid] = n
        return n


# ── Retrieval tools ─────────────────────────────────────────────

def semantic_search(query, ev, k=40, keep=6):
    """v2 pipeline: FAISS -> junk filters -> rerank -> dedup."""
    prefixed = f"search_query: {query}"
    qv = model.encode([prefixed], normalize_embeddings=True).astype("float32")
    scores, indices = index.search(qv, k)
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(texts) or junk(texts[idx], metadatas[idx]):
            continue
        results.append({"cid": int(idx), "text": texts[idx], "meta": metadatas[idx], "score": float(score)})
    if len(results) >= 2:
        ce = np.array(reranker.predict([(query, r["text"]) for r in results]), dtype=float)
        emb = np.array([r["score"] for r in results], dtype=float)
        z = lambda x: (x - x.mean()) / (x.std() + 1e-9)
        final = 0.6 * z(emb) + 0.4 * z(ce)
        for r, s in zip(results, final):
            r["score"] = float(s)
        results.sort(key=lambda r: -r["score"])
    seen, title_counts, out = set(), {}, []
    for r in results:
        key = r["text"][:150].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        title = r["meta"].get("title", "")
        if title_counts.get(title, 0) >= 2:
            continue
        title_counts[title] = title_counts.get(title, 0) + 1
        out.append(r)
        if len(out) >= keep:
            break
    lines = []
    for r in out:
        n = ev.add(r["cid"], r["text"], r["meta"])
        lines.append(f"[{n}] {format_citation_short(r['meta'])}\n{r['text'][:900]}")
    return "\n\n".join(lines) if lines else "No results."


def _fts_query(q):
    """Make the query FTS5-safe: quoted phrases pass through, bare words get quoted."""
    q = q.strip()
    if any(op in q for op in ('"', ' AND ', ' OR ', ' NOT ')):
        return q
    words = re.findall(r"[A-Za-z0-9'’-]+", q)
    return " ".join(f'"{w}"' for w in words) if words else q


def exact_search(query, ev, limit=8):
    """Literal / boolean full-text search. Finds phrases vector search misses."""
    try:
        with fts_lock:
            rows = fts.execute(
                "SELECT cid, snippet(chunks, 0, '«', '»', ' … ', 40) FROM chunks "
                "WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
                (_fts_query(query), int(limit)),
            ).fetchall()
    except sqlite3.OperationalError as e:
        return f"Search syntax error: {e}. Use plain words or \"quoted phrases\"."
    lines = []
    for cid, snip in rows:
        cid = int(cid)
        n = ev.add(cid, texts[cid], metadatas[cid])
        lines.append(f"[{n}] {format_citation_short(metadatas[cid])}\n…{snip}…")
    return "\n\n".join(lines) if lines else "No literal matches."


def read_context(cid, ev, radius=1):
    """Read a chunk plus its neighbours in the same work (page context)."""
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return "read_context needs the numeric id shown in brackets, e.g. 1234."
    if not (0 <= cid < len(texts)):
        return f"No chunk {cid}."
    radius = max(0, min(int(radius or 1), 2))
    title = metadatas[cid].get("title")
    parts = []
    for i in range(cid - radius, cid + radius + 1):
        if 0 <= i < len(texts) and metadatas[i].get("title") == title:
            n = ev.add(i, texts[i], metadatas[i])
            parts.append(f"[{n}] {format_citation_short(metadatas[i])}\n{texts[i][:1100]}")
    return "\n\n".join(parts)


def term_timeline(term):
    """Where and when a term appears: counts per year and work."""
    try:
        with fts_lock:
            rows = fts.execute(
                "SELECT year, title, count(*) FROM chunks WHERE chunks MATCH ? "
                "GROUP BY year, title ORDER BY year",
                (_fts_query(term),),
            ).fetchall()
    except sqlite3.OperationalError as e:
        return f"Search syntax error: {e}."
    if not rows:
        return "Term not found anywhere in the corpus."
    lines = [f"{y} — {t}: {c} passage(s)" for y, t, c in rows[:60]]
    if len(rows) > 60:
        lines.append(f"…and {len(rows) - 60} more works.")
    return "\n".join(lines)


# ── Exploration agent ───────────────────────────────────────────
TOOLS_SPEC = [
    {"type": "function", "function": {
        "name": "semantic_search",
        "description": "Search the corpus by MEANING (embeddings + reranker). Best for concepts and topics, even when Kantor used different words.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "A natural-language description of what to find"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "exact_search",
        "description": "Search the corpus for LITERAL text (full-text index). Best for exact phrases in double quotes, names (Skinner, Watson), rare terms. Supports AND / OR / NOT.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Words, \"quoted phrase\", or boolean query"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read_context",
        "description": "Read the full text around a passage you already found, to see the argument before and after it.",
        "parameters": {"type": "object", "properties": {
            "cid": {"type": "integer", "description": "The numeric id shown in [brackets] in earlier results"},
            "radius": {"type": "integer", "description": "How many neighbouring chunks on each side (1-2)"}},
            "required": ["cid"]}}},
    {"type": "function", "function": {
        "name": "term_timeline",
        "description": "See in which years and works a term appears, with counts. Ideal for questions about how a concept evolved over time.",
        "parameters": {"type": "object", "properties": {
            "term": {"type": "string", "description": "The term or \"quoted phrase\" to trace"}},
            "required": ["term"]}}},
]

AGENT_SYSTEM = """You are a research assistant exploring the complete works of J.R. Kantor \
(interbehavioral psychology): 20 books, 91 articles, 21 reviews, fully indexed.

You have search tools. Work like a scholar in an archive:
1. Plan: decide what evidence would answer the question.
2. Explore in several rounds. Combine tools: exact_search for phrases and names, \
semantic_search for concepts, term_timeline for chronology, read_context to verify \
a quote's surroundings before citing it.
3. If a search returns nothing useful, rephrase and try again — different words, \
narrower phrases, related terms.
4. Stop when you have enough evidence, then write the final answer.

Rules for the final answer:
- Cite every substantive claim with the bracketed numbers from the search results, e.g. [3].
- Quote Kantor's exact words (short quotes) when the question is about wording.
- If sources show his thinking changing over time, present it chronologically with years.
- Never invent quotes, page numbers, or references. Only cite numbers you actually saw.
- If the evidence is incomplete, say plainly what was and wasn't found.
- Write clear academic prose, accessible to students."""


def run_exploration(query, progress_cb):
    """Multi-round tool-calling loop. Returns (answer_md, evidence)."""
    ev = Evidence()
    tool_impl = {
        "semantic_search": lambda a: semantic_search(a.get("query", ""), ev),
        "exact_search": lambda a: exact_search(a.get("query", ""), ev),
        "read_context": lambda a: read_context(a.get("cid"), ev, a.get("radius", 1)),
        "term_timeline": lambda a: term_timeline(a.get("term", "")),
    }
    nice = {"semantic_search": "Searching by meaning", "exact_search": "Searching exact text",
            "read_context": "Reading page context", "term_timeline": "Tracing term over time"}
    messages = [
        {"role": "system", "content": AGENT_SYSTEM},
        {"role": "user", "content": f"Question: {query}"},
    ]
    for round_no in range(1, MAX_ROUNDS + 1):
        force_answer = round_no == MAX_ROUNDS
        resp = groq_client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=None if force_answer else TOOLS_SPEC,
            tool_choice="none" if force_answer else "auto",
            temperature=0.3,
            max_tokens=1600,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return (msg.content or "").strip(), ev
        messages.append({"role": "assistant", "content": msg.content,
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            label = nice.get(tc.function.name, tc.function.name)
            detail = args.get("query") or args.get("term") or (f"passage {args.get('cid')}" if args.get("cid") is not None else "")
            progress_cb(f"{label}: *{detail}*")
            try:
                result = tool_impl.get(tc.function.name, lambda a: "Unknown tool.")(args)
            except Exception as e:  # keep exploring even if one tool call breaks
                result = f"Tool error: {e}"
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)[:8000]})
    return "The exploration ran out of rounds before producing an answer. Try Quick mode or rephrase.", ev


def run_quick(query):
    """Classic v2 single-pass pipeline (kept as-is, minus display code)."""
    ev = Evidence()
    context_block = semantic_search(query, ev, k=40, keep=8)
    if context_block == "No results.":
        return "No relevant passages found for this query. Try rephrasing your question.", ev
    refs = "\n".join(f"- [{it['n']}] {format_citation_short(it['meta'])}" for it in ev.items)
    resp = groq_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": f"""You are a research assistant specializing in J.R. Kantor's \
interbehavioral psychology. Answer ONLY from the provided excerpts.
Cite claims with the bracketed numbers, e.g. [2]. Never invent references.
If the excerpts don't fully address the question, say what IS covered.
Available sources:\n{refs}"""},
            {"role": "user", "content": f"Excerpts:\n{context_block}\n\nQuestion: {query}"},
        ],
        temperature=0.4, max_tokens=1200, frequency_penalty=0.3,
    )
    return (resp.choices[0].message.content or "").strip(), ev


def render_sources(ev):
    if not ev.items:
        return ""
    out = []
    for it in ev.items:
        text = it["text"]
        display = text[:600] + "…" if len(text) > 600 else text
        citation_html = re.sub(r"\*(.+?)\*", r"<i>\1</i>", format_citation(it["meta"]))
        out.append(
            f"<div class='src'><span class='src-n'>{it['n']}</span> {citation_html}"
            f"<details><summary>View passage</summary>\n\n{display}\n\n</details></div>"
        )
    return "\n".join(out)


def search_and_answer(query, mode):
    """Gradio generator: yields (status, answer, sources)."""
    if not query or len(query.strip()) < 3:
        yield "", "Please enter a research question (at least 3 characters).", ""
        return
    if STUB_LLM:
        ev = Evidence()
        hits = exact_search(query, ev)
        yield "", f"**[Local test — no LLM]** Literal matches for your query:\n\n{hits}", render_sources(ev)
        return
    steps = []
    try:
        if mode == "Deep exploration":
            answer_holder = {}
            import queue as _q
            events = _q.Queue()

            def cb(s):
                events.put(s)

            import threading as _t

            def work():
                try:
                    answer_holder["ans"], answer_holder["ev"] = run_exploration(query, cb)
                except Exception as e:
                    answer_holder["err"] = str(e)
                events.put(None)

            _t.Thread(target=work, daemon=True).start()
            while True:
                s = events.get()
                if s is None:
                    break
                steps.append(s)
                trail = "\n".join(f"<div class='step'>{x}</div>" for x in steps)
                yield f"<div class='steps'>{trail}<div class='step live'>Reading results…</div></div>", "", ""
            if "err" in answer_holder:
                raise RuntimeError(answer_holder["err"])
            answer, ev = answer_holder["ans"], answer_holder["ev"]
            trail = "\n".join(f"<div class='step done'>{x}</div>" for x in steps)
            yield f"<div class='steps closed'>{trail}</div>", answer, render_sources(ev)
        else:
            yield "<div class='steps'><div class='step live'>Searching…</div></div>", "", ""
            answer, ev = run_quick(query)
            yield "", answer, render_sources(ev)
    except Exception as e:
        yield "", f"An error occurred: {e}\n\nPlease try again or rephrase your question.", ""


def set_query_and_search(question, mode):
    for status, answer, sources in search_and_answer(question, mode):
        yield question, status, answer, sources


# ── Bibliography ────────────────────────────────────────────────

def build_bibliography():
    bib, seen = {}, set()
    for meta in metadatas:
        key = f"{meta.get('year', '')}_{meta.get('title', 'Unknown')}"
        if key in seen:
            continue
        seen.add(key)
        label = TYPE_LABELS.get(meta.get("type", "Other"), meta.get("type", "Other"))
        bib.setdefault(label, []).append(f"Kantor, J.R. ({meta.get('year', '')}). *{meta.get('title', 'Unknown')}*")
    return {k: sorted(set(v)) for k, v in bib.items()}


BIBLIOGRAPHY = build_bibliography()

EXAMPLE_QUESTIONS = [
    "What is Kantor's view on the mind-body problem?",
    "How does Kantor define stimulus function and response function?",
    "What did Kantor think about Skinner and operant conditioning?",
    "How did the concept of the behavior segment evolve across his works?",
    "How does Kantor critique mentalism in psychology?",
    "Where does Kantor discuss the relationship between psychology and physics?",
]

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,400&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&family=Inter:wght@400;500;600&display=swap');

:root {
    --paper: #FAF8F4;
    --ink: #23201C;
    --muted: #7A736B;
    --faint: #A39B92;
    --accent: #7A2E2E;
    --accent-soft: #F3E9E7;
    --line: #E6E0D8;
    --display: 'Fraunces', Georgia, serif;
    --serif: 'Newsreader', Georgia, serif;
    --sans: 'Inter', -apple-system, sans-serif;
}

html, body { height:auto!important; min-height:0!important; overflow-x:hidden!important; background:var(--paper)!important; }
gradio-app { display:block!important; height:auto!important; background:var(--paper)!important; }
.gradio-container {
    font-family:var(--serif)!important; color:var(--ink)!important;
    max-width:760px!important; margin:0 auto!important;
    height:auto!important; min-height:0!important; overflow:visible!important;
    padding:0 1.25rem 3rem!important; background:var(--paper)!important;
}
.gradio-container .main, .gradio-container .contain, .gradio-container .wrap, .gradio-container .app {
    height:auto!important; max-height:none!important; overflow:visible!important; background:transparent!important;
}
.gradio-container .block, .gradio-container .form, .gradio-container .gap {
    background:transparent!important; border:none!important; box-shadow:none!important;
}
footer { display:none!important; }

/* ── Masthead: quiet, left-aligned, like a journal ── */
.masthead { padding:3.2rem 0 0; }
.masthead .eyebrow {
    font-family:var(--sans); font-size:0.72rem; letter-spacing:0.22em; text-transform:uppercase;
    color:var(--accent); margin:0 0 0.9rem;
}
.masthead h1 {
    font-family:var(--display)!important; font-weight:500!important; font-size:2.6rem!important;
    line-height:1.15!important; letter-spacing:-0.01em; color:var(--ink)!important; margin:0 0 0.7rem!important;
}
.masthead .dek {
    font-family:var(--serif); font-size:1.12rem; line-height:1.65; color:var(--muted);
    max-width:56ch; margin:0 0 1.1rem;
}
.masthead .stats {
    font-family:var(--sans); font-size:0.78rem; color:var(--faint); letter-spacing:0.04em;
}
.masthead .stats b { color:var(--muted); font-weight:600; }
.rule { border:none; border-top:1px solid var(--line); margin:1.6rem 0 1.4rem; }

/* ── Search ── */
.gradio-container textarea, .gradio-container input[type="text"] {
    font-family:var(--serif)!important; font-size:1.15rem!important; color:var(--ink)!important;
    background:#fff!important; border:1px solid var(--line)!important; border-radius:10px!important;
    padding:0.9rem 1rem!important; box-shadow:0 1px 2px rgba(35,32,28,0.04)!important;
    transition:border-color .15s ease, box-shadow .15s ease;
}
.gradio-container textarea:focus {
    border-color:var(--accent)!important; box-shadow:0 0 0 3px rgba(122,46,46,0.10)!important; outline:none!important;
}
.gradio-container textarea::placeholder { color:var(--faint)!important; font-style:italic; }

.primary-btn button, .primary-btn {
    background:var(--ink)!important; color:var(--paper)!important; border:none!important;
    border-radius:10px!important; min-height:48px!important;
    font-family:var(--sans)!important; font-weight:500!important; font-size:0.95rem!important;
    letter-spacing:0.02em; box-shadow:none!important; transition:background .15s ease;
}
.primary-btn button:hover, .primary-btn:hover { background:#3A342E!important; }

/* ── Mode toggle: quiet segmented control ── */
.mode-radio { margin-top:0.2rem!important; }
.mode-radio .wrap { gap:0.4rem!important; }
.mode-radio label {
    font-family:var(--sans)!important; font-size:0.85rem!important; color:var(--muted)!important;
    background:transparent!important; border:1px solid var(--line)!important; border-radius:999px!important;
    padding:0.35rem 0.9rem!important; box-shadow:none!important;
}
.mode-radio label.selected {
    background:var(--accent-soft)!important; border-color:var(--accent)!important; color:var(--accent)!important;
}
.mode-radio input { display:none!important; }
.mode-hint { font-family:var(--sans); font-size:0.78rem; color:var(--faint); margin-top:0.15rem; }

/* ── Example questions: a plain list, not chips ── */
.examples-title {
    font-family:var(--sans); font-size:0.72rem; letter-spacing:0.18em; text-transform:uppercase;
    color:var(--faint); margin:1.4rem 0 0.4rem;
}
.example-btn button {
    all:unset!important; display:block!important; cursor:pointer!important;
    font-family:var(--serif)!important; font-size:1.02rem!important; font-style:italic;
    color:var(--accent)!important; line-height:1.5!important; padding:0.28rem 0!important;
    border-bottom:none!important; text-align:left!important; width:100%!important;
}
.example-btn button:hover { color:#5C1F1F!important; text-decoration:underline; text-underline-offset:3px; }
.example-btn { margin:0!important; min-height:0!important; }
.example-btn + .example-btn { margin-top:-0.55rem!important; }

/* ── Exploration trail ── */
.steps { margin:1rem 0 0; padding:0.2rem 0 0.2rem 1rem; border-left:2px solid var(--line); }
.step {
    font-family:var(--sans); font-size:0.85rem; color:var(--muted); padding:0.18rem 0;
}
.step em { color:var(--ink); font-style:normal; font-weight:500; }
.step.live { color:var(--accent); }
.step.live::after { content:' ·'; animation:blink 1s infinite; }
@keyframes blink { 50% { opacity:0.2; } }
.steps.closed .step { color:var(--faint); }

/* ── Answer: typeset like an article, no box ── */
.answer-area { margin-top:1.2rem; }
.answer-area p, .answer-area li {
    font-family:var(--serif)!important; font-size:1.13rem!important; line-height:1.78!important; color:var(--ink)!important;
}
.answer-area h1, .answer-area h2, .answer-area h3 {
    font-family:var(--display)!important; font-weight:500!important; color:var(--ink)!important;
}

/* ── Sources: footnote style ── */
.sources-title {
    font-family:var(--sans); font-size:0.72rem; letter-spacing:0.18em; text-transform:uppercase;
    color:var(--faint); margin:2rem 0 0.6rem; padding-top:1.2rem; border-top:1px solid var(--line);
}
.src {
    font-family:var(--serif); font-size:0.98rem; line-height:1.6; color:var(--ink);
    padding:0.45rem 0; border-bottom:1px solid var(--line);
}
.src-n {
    display:inline-block; min-width:1.5rem; font-family:var(--sans); font-size:0.8rem;
    font-weight:600; color:var(--accent);
}
.src details { margin:0.3rem 0 0 1.6rem; background:transparent; border:none; padding:0; }
.src details summary {
    cursor:pointer; font-family:var(--sans); font-size:0.8rem; color:var(--muted); font-weight:500;
}
.src details summary:hover { color:var(--accent); }
.src details[open] { background:#fff; border:1px solid var(--line); border-radius:8px; padding:0.7rem 0.9rem; }

/* ── Bibliography ── */
.bib-title {
    font-family:var(--sans); font-size:0.72rem; letter-spacing:0.18em; text-transform:uppercase;
    color:var(--faint); margin:2.6rem 0 0.3rem; padding-top:1.4rem; border-top:1px solid var(--line);
}
.bib-note { font-family:var(--serif); font-size:0.95rem; color:var(--muted); font-style:italic; }
.gradio-container .accordion, .gradio-container [class*="accordion"] {
    border:none!important; border-bottom:1px solid var(--line)!important; border-radius:0!important;
    background:transparent!important; margin:0!important;
}
.gradio-container .label-wrap {
    flex-direction:row-reverse!important; justify-content:flex-end!important; gap:0.6rem!important;
    align-items:center!important; padding:0.65rem 0!important; background:transparent!important;
}
.gradio-container .label-wrap span {
    font-family:var(--sans)!important; font-size:0.92rem!important; font-weight:500!important; color:var(--ink)!important;
}
.gradio-container .label-wrap .icon { color:var(--faint)!important; margin:0!important; }
.gradio-container .accordion p, .gradio-container .accordion li {
    font-size:0.95rem!important; line-height:1.65!important; color:var(--muted)!important;
}

/* ── Footer ── */
.footer-text {
    text-align:left; font-family:var(--sans); color:var(--faint); font-size:0.8rem; padding:2.2rem 0 0.4rem;
}
.footer-text a { color:var(--muted); text-decoration:none; border-bottom:1px solid var(--line); }
.footer-text a:hover { color:var(--accent); border-color:var(--accent); }
"""

ENTER_JS = """
() => {
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            const textarea = document.querySelector('textarea');
            if (textarea && document.activeElement === textarea) {
                e.preventDefault();
                const btn = document.querySelector('.primary-btn button, button.primary-btn');
                if (btn) btn.click();
            }
        }
    });
}
"""

with gr.Blocks(css=CUSTOM_CSS, title="J.R. Kantor Research System", theme=gr.themes.Base(), js=ENTER_JS) as demo:
    gr.HTML(f"""
    <div class="masthead">
        <p class="eyebrow">Interbehavioral Psychology Archive</p>
        <h1>The Works of J.&thinsp;R.&thinsp;Kantor</h1>
        <p class="dek">Ask a research question and the system reads across sixty years
        of Kantor's books, articles and columns to answer it — with passages and page numbers.</p>
        <p class="stats"><b>20</b> books &nbsp;·&nbsp; <b>91</b> articles &nbsp;·&nbsp; <b>21</b> reviews
        &nbsp;·&nbsp; {index_summary.get('total_chunks', len(texts))} indexed passages &nbsp;·&nbsp; 1915–1987</p>
    </div>
    <hr class="rule">
    """)

    with gr.Row():
        query_input = gr.Textbox(
            show_label=False,
            placeholder="e.g., Where does Kantor first define the behavior segment?",
            lines=1, scale=4, container=False,
        )
        search_btn = gr.Button("Search", scale=1, elem_classes="primary-btn")

    mode_radio = gr.Radio(
        ["Deep exploration", "Quick search"], value="Deep exploration",
        show_label=False, elem_classes="mode-radio", container=False,
    )
    gr.HTML("""<p class="mode-hint">Deep exploration reads the archive in several rounds — better for exact
    quotes, names, and how ideas changed over time. Quick search is a single pass.</p>""")

    gr.HTML('<p class="examples-title">Try a question</p>')
    ex_buttons = []
    for q in EXAMPLE_QUESTIONS:
        with gr.Row(elem_classes="example-btn"):
            ex_buttons.append(gr.Button(q, size="sm"))

    status_output = gr.HTML()
    with gr.Column(elem_classes="answer-area"):
        answer_output = gr.Markdown()
    sources_header = gr.HTML(visible=False)
    sources_output = gr.HTML()

    def _with_header(gen):
        """Show the 'Sources' header only when there are sources."""
        for status, answer, sources in gen:
            header = '<p class="sources-title">Sources &amp; passages</p>' if sources else ""
            yield status, answer, gr.update(value=header, visible=bool(sources)), sources

    def on_search(query, mode):
        yield from _with_header(search_and_answer(query, mode))

    def on_example(q, mode):
        for question, status, answer, sources in set_query_and_search(q, mode):
            header = '<p class="sources-title">Sources &amp; passages</p>' if sources else ""
            yield question, status, answer, gr.update(value=header, visible=bool(sources)), sources

    search_btn.click(on_search, [query_input, mode_radio],
                     [status_output, answer_output, sources_header, sources_output])
    query_input.submit(on_search, [query_input, mode_radio],
                       [status_output, answer_output, sources_header, sources_output])
    for btn, q in zip(ex_buttons, EXAMPLE_QUESTIONS):
        btn.click(on_example, [gr.State(q), mode_radio],
                  [query_input, status_output, answer_output, sources_header, sources_output])

    gr.HTML('<p class="bib-title">Indexed works</p>')
    gr.HTML(f'<p class="bib-note">{index_summary.get("total_entries", "?")} works currently indexed. '
            f'Additional bibliography entries are pending digitization.</p>')
    type_order = ["Book", "Article", "Observer Column", "Book Review"]
    for label in type_order + sorted(k for k in BIBLIOGRAPHY if k not in type_order):
        if label in BIBLIOGRAPHY:
            items = BIBLIOGRAPHY[label]
            with gr.Accordion(f"{label}s ({len(items)})" if not label.endswith("s") else f"{label} ({len(items)})", open=False):
                gr.Markdown("\n".join(f"- {item}" for item in items))

    gr.HTML("""
    <div class="footer-text">
        <a href="https://interbehavioral.com" target="_blank">interbehavioral.com</a> &nbsp;·&nbsp;
        <a href="https://interbehavioral.com/contact/" target="_blank">Feedback</a>
    </div>
    """)


if __name__ == "__main__":
    demo.launch()
