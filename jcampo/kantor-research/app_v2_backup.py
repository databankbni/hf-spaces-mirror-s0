r"""
J.R. Kantor Research System — Hugging Face Spaces App (v2)
==========================================================
Powered by:
  - Embeddings: nomic-ai/nomic-embed-text-v1.5 (768-dim, 8192 token context)
  - LLM: Groq llama-3.3-70b-versatile
  - Vector DB: FAISS (local, cosine similarity via inner product)
  - Frontend: Gradio with dark red academic theme
  - Index: Page-aware chunking with page number metadata
"""

import gradio as gr
import os
import re
import json
import pickle
import numpy as np
import faiss
from groq import Groq
from sentence_transformers import SentenceTransformer, CrossEncoder

# ── Config ──────────────────────────────────────────────────────
DB_DIR = "./database"
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1.5"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ── Initialize ──────────────────────────────────────────────────
print("Loading embedding model...")
model = SentenceTransformer(EMBEDDING_MODEL, trust_remote_code=True)
print(f"Model loaded: {EMBEDDING_MODEL} (dim={model.get_sentence_embedding_dimension()})")

print("Loading reranker model...")
reranker = CrossEncoder(RERANKER_MODEL, max_length=512)
print(f"Reranker loaded: {RERANKER_MODEL}")

print("Loading FAISS index...")
index = faiss.read_index(os.path.join(DB_DIR, "index.faiss"))
print(f"FAISS index: {index.ntotal} vectors")

print("Loading metadata...")
with open(os.path.join(DB_DIR, "index_data.pkl"), "rb") as f:
    data = pickle.load(f)
texts = data["texts"]
metadatas = data["metadatas"]
print(f"Metadata loaded: {len(texts)} chunks")

# Load summary for stats
summary_path = os.path.join(DB_DIR, "index_summary.json")
if os.path.exists(summary_path):
    with open(summary_path) as f:
        index_summary = json.load(f)
else:
    index_summary = {"total_chunks": len(texts), "total_entries": "?", "types": {}}

print("Initializing Groq client...")
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
print("System ready!")


# ── Search & Answer ─────────────────────────────────────────────

TYPE_LABELS = {
    "Book": "Book",
    "Article": "Article",
    "Review": "Book Review",
    "Observer": "Observer Column",
}


def format_page_ref(meta):
    """Format page reference from metadata."""
    start = meta.get("start_page")
    end = meta.get("end_page")
    if not start:
        return ""
    if start == end or not end:
        return f"p. {start}"
    return f"pp. {start}–{end}"


def format_citation(meta):
    """Build clean APA-style citation with page numbers."""
    title = meta.get("title", "Unknown").strip()
    year = meta.get("year", "n.d.")
    doc_type = meta.get("type", "")
    label = TYPE_LABELS.get(doc_type, doc_type)
    page_ref = format_page_ref(meta)

    citation = f"Kantor, J.R. ({year}). *{title}* [{label}]"
    if page_ref:
        citation += f", {page_ref}"
    return citation


def format_citation_for_llm(meta):
    """Shorter citation for the LLM context window."""
    title = meta.get("title", "Unknown").strip()
    year = meta.get("year", "n.d.")
    page_ref = format_page_ref(meta)
    cite = f"Kantor ({year}), \"{title}\""
    if page_ref:
        cite += f", {page_ref}"
    return cite


def is_valid_chunk(text):
    """Filter out chunks that are just punctuation, numbers, or metadata."""
    if not text or len(text.strip()) < 30:
        return False
    alphanumeric = re.sub(r"[^a-zA-Z]", "", text)
    return len(alphanumeric) >= 20


def is_metadata_heavy(text, meta):
    """Detect chunks that are mostly title/abstract/journal metadata.
    These match keywords well but contain little substantive content."""
    t = text.lower()
    if 'requests for reprints' in t:
        return True
    # Page 1 chunks with telltale signs of abstracts/headers
    if meta.get('start_page', 0) == 1:
        signals = 0
        if 'abstract' in t: signals += 2
        if 'resumen' in t: signals += 2
        if 'vol.' in t or 'vol ' in t: signals += 1
        if 'pp.' in t or 'pp ' in t: signals += 1
        if 'university' in t and 'indiana' in t.lower(): signals += 1
        if 'revista' in t or 'journal' in t: signals += 1
        if signals >= 3:
            return True
    return False


def is_reference_list(text):
    """Detect chunks that are bibliography / reference-list pages.
    They are dense with citations and match keywords, but contain no
    substantive discussion."""
    # Repeated author citations ("Kantor, J. R." / "Kantor, J.R.")
    author_cites = len(re.findall(r"Kantor,\s*J\.?\s*R\.?", text))
    if author_cites >= 3:
        return True
    # Journal citation pattern: "1922, 19, 38-49" (year, volume, pages)
    journal_cites = len(re.findall(r"\b1[89]\d{2},\s*\d+,\s*\d+", text))
    if journal_cites >= 3:
        return True
    # High density of years (typical of reference pages)
    years = len(re.findall(r"\b1[89]\d{2}\b", text))
    if years >= 6 and years / max(len(text) / 100.0, 1.0) > 1.0:
        return True
    return False


def word_quality(text):
    """Fraction of tokens that look like real words. Low values indicate
    badly OCR'd pages that pollute results."""
    tokens = re.findall(r"[A-Za-z]+", text)
    if not tokens:
        return 0.0
    good = sum(1 for t in tokens
               if len(t) >= 2 and (t.islower() or t.istitle()
                                   or (t.isupper() and len(t) <= 4)))
    return good / len(tokens)


def search_faiss(query, k=40):
    """Search FAISS with nomic embeddings. Skips junk chunks
    (reference lists, title pages, metadata-heavy or badly OCR'd pages)."""
    prefixed = f"search_query: {query}"
    query_vec = model.encode([prefixed], normalize_embeddings=True).astype("float32")
    scores, indices = index.search(query_vec, k)
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(texts):
            continue
        text = texts[idx]
        meta = metadatas[idx]
        if not is_valid_chunk(text):
            continue
        if is_reference_list(text):
            continue
        if is_metadata_heavy(text, meta):
            continue
        if word_quality(text) < 0.78:
            continue
        results.append({
            "text": text,
            "meta": meta,
            "score": float(score),
        })
    return results


def rerank_results(query, results, keep=16):
    """Re-score candidates with a cross-encoder and blend with the
    embedding score. The blend keeps the strengths of both: embeddings
    capture topic, the cross-encoder captures actual relevance."""
    if len(results) < 2:
        return results
    pairs = [(query, r["text"]) for r in results]
    ce_scores = np.array(reranker.predict(pairs), dtype=float)
    emb_scores = np.array([r["score"] for r in results], dtype=float)

    def z(x):
        return (x - x.mean()) / (x.std() + 1e-9)

    final = 0.6 * z(emb_scores) + 0.4 * z(ce_scores)
    for r, s in zip(results, final):
        r["rerank_score"] = float(s)
    results.sort(key=lambda r: -r["rerank_score"])
    return results[:keep]


def deduplicate_results(results, max_results=8):
    """Deduplicate by content similarity AND by title.
    - Skip chunks with near-identical text (catches journal issue duplicates)
    - Allow up to 2 chunks from the same work"""
    seen_text_starts = set()
    title_counts = {}
    unique = []

    for r in results:
        # Content dedup: skip if first 150 chars match something already selected
        text_key = r["text"][:150].strip().lower()
        if text_key in seen_text_starts:
            continue
        seen_text_starts.add(text_key)

        # Title dedup: max 2 per work
        title = r["meta"].get("title", "")
        count = title_counts.get(title, 0)
        if count >= 2:
            continue
        title_counts[title] = count + 1
        unique.append(r)

        if len(unique) >= max_results:
            break

    return unique


def search_and_answer(query):
    """Main RAG pipeline: search -> context -> LLM -> answer."""
    if not query or len(query.strip()) < 3:
        return "Please enter a research question (at least 3 characters).", ""

    try:
        results = search_faiss(query, k=40)
        reranked = rerank_results(query, results, keep=16)
        unique_results = deduplicate_results(reranked, max_results=8)

        if not unique_results:
            return "No relevant passages found for this query. Try rephrasing your question.", ""

        # Build context for LLM
        context = ""
        source_refs = ""
        sources_display = []

        for i, r in enumerate(unique_results, 1):
            llm_citation = format_citation_for_llm(r["meta"])
            display_citation = format_citation(r["meta"])

            context += f"\n[Source {i}: {llm_citation}]\n{r['text']}\n"
            source_refs += f"- Source {i}: {llm_citation}\n"
            sources_display.append({
                "num": i,
                "citation": display_citation,
                "text": r["text"],
            })

        # LLM call
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": f"""You are a research assistant specializing in J.R. Kantor's interbehavioral psychology. Your audience includes students, researchers, and academics exploring Kantor's work.

Answer the question based ONLY on the provided source excerpts from Kantor's works.

Guidelines:
1. Cite every substantive claim using [Source X] notation.
2. Synthesize across multiple sources when they address the same topic.
3. Use clear academic prose — be thorough but accessible.
4. If different sources show how Kantor's thinking evolved over time, note this.
5. Do NOT cite authors other than Kantor unless they appear in the excerpts.
6. Do NOT invent or fabricate any references.
7. If the excerpts don't fully address the question, state what IS covered and note the limitation.

Available sources:
{source_refs}"""
                },
                {
                    "role": "user",
                    "content": f"Excerpts from Kantor's works:\n{context}\n\nQuestion: {query}"
                }
            ],
            temperature=0.4,
            max_tokens=1200,
            frequency_penalty=0.3,
        )

        answer = response.choices[0].message.content

        # Build sources display
        sources_md = ""
        for s in sources_display:
            sources_md += f"**Source {s['num']}:** {s['citation']}\n\n"
            display_text = s["text"][:600] + "..." if len(s["text"]) > 600 else s["text"]
            sources_md += f"<details><summary>View passage</summary>\n\n{display_text}\n\n</details>\n\n---\n\n"

        return answer, sources_md

    except Exception as e:
        return f"An error occurred: {str(e)}\n\nPlease try again or rephrase your question.", ""


def set_query_and_search(question):
    """Helper for example buttons."""
    answer, sources = search_and_answer(question)
    return question, answer, sources


# ── Bibliography ────────────────────────────────────────────────

def build_bibliography():
    """Build bibliography from indexed metadata."""
    bib = {}
    seen = set()
    for meta in metadatas:
        title = meta.get("title", "Unknown")
        year = meta.get("year", "")
        key = f"{year}_{title}"
        if key in seen:
            continue
        seen.add(key)
        doc_type = meta.get("type", "Other")
        label = TYPE_LABELS.get(doc_type, doc_type)
        if label not in bib:
            bib[label] = []
        bib[label].append(f"Kantor, J.R. ({year}). *{title}*")
    for label in bib:
        bib[label] = sorted(set(bib[label]))
    return bib

BIBLIOGRAPHY = build_bibliography()


# ── Gradio Interface ────────────────────────────────────────────

EXAMPLE_QUESTIONS = [
    "What is Kantor's view on the mind-body problem?",
    "How does Kantor define stimulus function and response function?",
    "What is the interbehavioral field and what are its components?",
    "How does Kantor critique mentalism in psychology?",
    "What is Kantor's position on the relationship between psychology and physics?",
    "How does Kantor approach the study of language and linguistics?",
]

CUSTOM_CSS = """
/* ── Fonts ─────────────────────────────────────────────────────
   Newsreader: a literary serif for headings + reading text.
   Inter: a clean sans for UI chrome (labels, buttons, stats). */
@import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,400&family=Inter:wght@400;500;600;700&display=swap');

:root {
    --kantor-red: #8B1A1A;
    --kantor-red-deep: #6E1212;
    --kantor-red-bright: #A52A2A;
    --kantor-red-wash: #FBF3F3;
    --ink: #2A2320;
    --muted: #6F6A66;
    --line: #ECE3E3;
    --serif: 'Newsreader', Georgia, 'Times New Roman', serif;
    --sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* ── Kill the inner scrollbar: let content flow on one page ───── */
html, body {
    height: auto !important;
    min-height: 0 !important;
    overflow-x: hidden !important;
    background: #ffffff !important;
}
gradio-app {
    display: block !important;
    height: auto !important;
    background: #ffffff !important;
}
.gradio-container {
    font-family: var(--serif) !important;
    color: var(--ink) !important;
    max-width: 900px !important;
    margin: 0 auto !important;
    height: auto !important;
    min-height: 0 !important;
    overflow: visible !important;
    padding: 0 1.1rem 2.5rem !important;
}
.gradio-container .main,
.gradio-container .contain,
.gradio-container .wrap,
.gradio-container .app {
    height: auto !important;
    max-height: none !important;
    overflow: visible !important;
}

/* Hide Gradio's default footer ("Use via API · Built with Gradio") */
footer { display: none !important; }

/* ── Typography ───────────────────────────────────────────────── */
.gradio-container h1,
.gradio-container h2,
.gradio-container h3 {
    font-family: var(--serif) !important;
    color: var(--ink) !important;
    font-weight: 600 !important;
    letter-spacing: 0.2px;
}
.gradio-container p,
.gradio-container li {
    font-family: var(--serif) !important;
    font-size: 1.05rem;
    line-height: 1.7;
    color: var(--ink);
}
.gradio-container label span,
.gradio-container .stats,
.gradio-container button,
.footer-text { font-family: var(--sans) !important; }

/* ── Header ───────────────────────────────────────────────────── */
.header-container {
    background: linear-gradient(135deg, #6E1212 0%, #8B1A1A 48%, #A52A2A 100%);
    color: #fff;
    padding: 2.7rem 2rem 2.3rem;
    border-radius: 16px;
    margin: 1.2rem 0 1.5rem;
    text-align: center;
    box-shadow: 0 12px 34px rgba(110, 18, 18, 0.20);
}
.header-container h1 {
    font-family: var(--serif) !important;
    font-size: 2.5rem;
    font-weight: 600;
    margin: 0 0 0.45rem 0;
    color: #ffffff !important;
    letter-spacing: 0.3px;
}
.header-container .subtitle {
    font-family: var(--sans) !important;
    font-size: 1.04rem;
    font-weight: 400;
    color: rgba(255, 255, 255, 0.93) !important;
    margin: 0.2rem 0;
}
.header-container .lang-note {
    font-family: var(--sans) !important;
    display: inline-block;
    margin-top: 0.9rem;
    padding: 0.28rem 0.85rem;
    border: 1px solid rgba(255, 255, 255, 0.45);
    border-radius: 999px;
    font-size: 0.8rem;
    letter-spacing: 0.3px;
    color: rgba(255, 255, 255, 0.92) !important;
}
.header-container .stats {
    font-family: var(--sans) !important;
    font-size: 0.78rem;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: rgba(255, 255, 255, 0.78) !important;
    margin-top: 0.9rem;
    font-style: normal;
}

/* ── Intro line ───────────────────────────────────────────────── */
.intro-text p {
    color: var(--muted) !important;
    font-size: 1.06rem;
    line-height: 1.7;
}

/* ── Search input ─────────────────────────────────────────────── */
.gradio-container textarea,
.gradio-container input[type="text"] {
    font-family: var(--serif) !important;
    font-size: 1.06rem !important;
    border-radius: 12px !important;
    border: 1.5px solid #E3D7D7 !important;
    background: #fff !important;
    transition: border-color .15s ease, box-shadow .15s ease;
}
.gradio-container textarea:focus,
.gradio-container input[type="text"]:focus {
    border-color: var(--kantor-red) !important;
    box-shadow: 0 0 0 3px rgba(139, 26, 26, 0.12) !important;
    outline: none !important;
}

/* ── Primary search button ────────────────────────────────────── */
.primary-btn, .primary-btn button {
    background: var(--kantor-red) !important;
    border: none !important;
    border-radius: 12px !important;
    min-height: 46px !important;
    font-family: var(--sans) !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px;
    color: #fff !important;
    box-shadow: 0 2px 8px rgba(139, 26, 26, 0.22) !important;
    transition: background .15s ease, transform .12s ease;
}
.primary-btn:hover, .primary-btn button:hover {
    background: var(--kantor-red-bright) !important;
    transform: translateY(-1px);
}

/* ── Example question chips ───────────────────────────────────── */
.example-btn button {
    border: 1px solid #E6D2D2 !important;
    color: var(--kantor-red) !important;
    background: #fff !important;
    font-family: var(--sans) !important;
    font-size: 0.9rem !important;
    font-weight: 500 !important;
    border-radius: 999px !important;
    padding: 0.55rem 1rem !important;
    box-shadow: none !important;
    transition: all .15s ease !important;
    white-space: normal !important;
    line-height: 1.35 !important;
}
.example-btn button:hover {
    background: var(--kantor-red-wash) !important;
    border-color: var(--kantor-red) !important;
    transform: translateY(-1px);
}

/* ── Answer ───────────────────────────────────────────────────── */
.answer-box {
    font-family: var(--serif) !important;
    background: #ffffff;
    border: 1px solid var(--line);
    border-left: 4px solid var(--kantor-red);
    border-radius: 10px;
    padding: 1.2rem 1.45rem;
    line-height: 1.8;
    font-size: 1.07rem;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}
.answer-box p { font-size: 1.07rem; line-height: 1.8; }

/* ── Disclosure caret on the LEFT for all accordions ──────────── */
.gradio-container .label-wrap {
    flex-direction: row-reverse !important;
    justify-content: flex-end !important;
    gap: 0.6rem !important;
    align-items: center !important;
}
.gradio-container .label-wrap .icon {
    color: var(--kantor-red) !important;
    margin: 0 !important;
}

/* Generic accordion frame (bibliography sections) */
.gradio-container .accordion,
.gradio-container [class*="accordion"] {
    border: 1px solid var(--line) !important;
    border-radius: 10px !important;
    margin: 0.4rem 0 !important;
}

/* "View passage" details inside the sources panel */
details {
    background: #FAFAFA;
    border: 1px solid #ECECEC;
    border-radius: 8px;
    padding: 0.75rem 0.9rem;
    margin: 0.35rem 0;
    font-family: var(--serif);
    font-size: 0.95rem;
    line-height: 1.6;
}
details summary {
    cursor: pointer;
    color: var(--kantor-red);
    font-weight: 600;
    font-family: var(--sans);
}

/* ── Sources accordion (red framed) ───────────────────────────── */
.sources-accordion {
    border: 1.5px solid var(--kantor-red) !important;
    border-radius: 12px !important;
    margin-top: 0.5rem !important;
    overflow: hidden !important;
}
.sources-accordion > .label-wrap {
    background-color: var(--kantor-red-wash) !important;
    padding: 0.85rem 1.1rem !important;
}
.sources-accordion > .label-wrap span {
    font-family: var(--sans) !important;
    font-weight: 600 !important;
    color: var(--kantor-red) !important;
    font-size: 1.02rem !important;
}
.sources-accordion > .label-wrap:hover {
    background-color: #F5E0E0 !important;
}

/* ── Footer ───────────────────────────────────────────────────── */
.footer-text {
    text-align: center;
    color: var(--muted);
    font-size: 0.85rem;
    padding: 1.2rem 0 0.4rem;
}
.footer-text a { color: var(--kantor-red); text-decoration: none; }
.footer-text a:hover { text-decoration: underline; }

/* Section dividers a touch softer */
.gradio-container hr { border: none; border-top: 1px solid var(--line); margin: 1.3rem 0; }
"""

ENTER_JS = """
() => {
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            const textarea = document.querySelector('textarea');
            if (textarea && document.activeElement === textarea) {
                e.preventDefault();
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    if (btn.textContent.trim() === 'Search') {
                        btn.click();
                        break;
                    }
                }
            }
        }
    });
}
"""

with gr.Blocks(css=CUSTOM_CSS, theme=gr.themes.Base(), js=ENTER_JS) as demo:

    gr.HTML(f"""
    <div class="header-container">
        <h1>J.R. Kantor Research System</h1>
        <div class="subtitle">Search through Kantor's complete works on interbehavioral psychology</div>
        <div class="lang-note">Questions welcome in English or Spanish &middot; Preguntas en inglés o español</div>
        <div class="stats">{index_summary.get('total_entries', '?')} Works &middot; {index_summary.get('total_chunks', '?'):,} Indexed Passages &middot; 1915&ndash;1984</div>
    </div>
    """)

    gr.Markdown("Enter a research question and the system will search across Kantor's indexed works, "
                "identify the most relevant passages, and generate a synthesized answer with citations.",
                elem_classes="intro-text")

    with gr.Row():
        query_input = gr.Textbox(
            label="Research Question",
            placeholder="e.g., What is Kantor's view on the mind-body problem?",
            lines=1,
            scale=4,
        )
        search_btn = gr.Button("Search", variant="primary", scale=1, elem_classes="primary-btn")

    gr.Markdown("**Example questions:**")
    with gr.Row(elem_classes="example-btn"):
        ex1 = gr.Button(EXAMPLE_QUESTIONS[0], size="sm")
        ex2 = gr.Button(EXAMPLE_QUESTIONS[1], size="sm")
        ex3 = gr.Button(EXAMPLE_QUESTIONS[2], size="sm")
    with gr.Row(elem_classes="example-btn"):
        ex4 = gr.Button(EXAMPLE_QUESTIONS[3], size="sm")
        ex5 = gr.Button(EXAMPLE_QUESTIONS[4], size="sm")
        ex6 = gr.Button(EXAMPLE_QUESTIONS[5], size="sm")

    gr.Markdown("---")

    answer_output = gr.Markdown(label="Answer", elem_classes="answer-box")

    with gr.Accordion("Sources & Passages", open=False, elem_classes="sources-accordion"):
        sources_output = gr.Markdown(label="Sources")

    search_btn.click(
        fn=search_and_answer,
        inputs=[query_input],
        outputs=[answer_output, sources_output],
    )
    query_input.submit(
        fn=search_and_answer,
        inputs=[query_input],
        outputs=[answer_output, sources_output],
    )

    for btn, q in [(ex1, EXAMPLE_QUESTIONS[0]), (ex2, EXAMPLE_QUESTIONS[1]),
                   (ex3, EXAMPLE_QUESTIONS[2]), (ex4, EXAMPLE_QUESTIONS[3]),
                   (ex5, EXAMPLE_QUESTIONS[4]), (ex6, EXAMPLE_QUESTIONS[5])]:
        btn.click(
            fn=set_query_and_search,
            inputs=[gr.State(q)],
            outputs=[query_input, answer_output, sources_output],
        )

    gr.Markdown("---")
    gr.Markdown("### Indexed Works")
    gr.Markdown(f"*{index_summary.get('total_entries', '?')} works currently indexed. "
                f"Additional bibliography entries are pending digitization.*")

    type_order = ["Book", "Article", "Observer Column", "Book Review"]

    for label in type_order:
        if label in BIBLIOGRAPHY:
            items = BIBLIOGRAPHY[label]
            with gr.Accordion(f"{label}s ({len(items)})", open=False):
                bib_text = "\n".join([f"- {item}" for item in items])
                gr.Markdown(bib_text)

    for label in sorted(BIBLIOGRAPHY.keys()):
        if label not in type_order:
            items = BIBLIOGRAPHY[label]
            with gr.Accordion(f"{label} ({len(items)})", open=False):
                bib_text = "\n".join([f"- {item}" for item in items])
                gr.Markdown(bib_text)

    gr.HTML("""
    <div class="footer-text">
        <a href="https://interbehavioral.com" target="_blank">interbehavioral.com</a> &middot;
        <a href="https://interbehavioral.com/contact/" target="_blank">Feedback</a>
    </div>
    """)


if __name__ == "__main__":
    demo.launch()

