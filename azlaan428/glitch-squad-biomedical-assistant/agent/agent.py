import sys, os, re, time, logging, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from retrieval.pubmed import fetch_pubmed

logger = logging.getLogger("aria.llm")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

VLLM_MODEL = "Qwen/Qwen2.5-72B-Instruct"
VLLM_PROBE_TIMEOUT = 3       # seconds to wait for the vLLM endpoint to answer
VLLM_PROBE_TTL = 30          # re-probe at most this often, so a busy pipeline
                              # (many get_llm() calls per query) doesn't pay a
                              # connection-timeout penalty on every single call

_backend_lock = threading.Lock()
_backend_state = {"backend": None, "checked_at": 0.0}


def _vllm_reachable(base_url):
    import requests
    try:
        resp = requests.get(base_url.rstrip("/") + "/models", timeout=VLLM_PROBE_TIMEOUT)
        return resp.status_code < 500
    except requests.RequestException as e:
        logger.warning(f"[ARIA] vLLM endpoint unreachable at {base_url}: {e}")
        return False


def _resolve_backend():
    """Decides vllm vs groq and caches the decision for VLLM_PROBE_TTL seconds."""
    now = time.time()
    with _backend_lock:
        if _backend_state["backend"] and (now - _backend_state["checked_at"]) < VLLM_PROBE_TTL:
            return _backend_state["backend"]

        vllm_base_url = os.environ.get("VLLM_BASE_URL")
        if vllm_base_url and _vllm_reachable(vllm_base_url):
            backend = "vllm"
            logger.info(f"[ARIA] Backend: AMD MI300X vLLM endpoint at {vllm_base_url} ({VLLM_MODEL})")
        else:
            if vllm_base_url:
                logger.warning(f"[ARIA] VLLM_BASE_URL={vllm_base_url} is set but unreachable, falling back to Groq")
            else:
                logger.info("[ARIA] VLLM_BASE_URL not set, using Groq")
            backend = "groq"
            logger.info("[ARIA] Backend: Groq (llama-3.1-8b-instant)")

        _backend_state["backend"] = backend
        _backend_state["checked_at"] = now
        return backend


def get_backend_status():
    """Reports which LLM backend is actually active, probing if not yet resolved."""
    if _resolve_backend() == "vllm":
        return {"backend": "vllm", "label": "Powered by Qwen2.5-72B on AMD MI300X"}
    return {"backend": "groq", "label": "Powered by Groq (llama-3.1-8b-instant) — AMD MI300X endpoint unavailable"}


def get_llm():
    if _resolve_backend() == "vllm":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=VLLM_MODEL,
            temperature=0,
            openai_api_key=os.environ.get("VLLM_API_KEY", "EMPTY"),
            openai_api_base=os.environ.get("VLLM_BASE_URL"),
        )

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set in environment")
    return ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0,
        api_key=key,
    )

def llm_invoke_with_retry(llm, prompt, max_retries=5):
    import time
    for attempt in range(max_retries):
        try:
            return llm.invoke(prompt)
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = 10 * (attempt + 1)
                print(f"[ARIA] Rate limit hit, waiting {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Max retries exceeded on rate limit")


@tool
def PubMedSearch(query: str) -> str:
    """Searches PubMed for biomedical literature abstracts."""
    results = fetch_pubmed(query, max_results=5)
    if not results:
        return "No abstracts found for this query."
    out = []
    for r in results:
        out.append("[PMID " + r["pmid"] + "]\n" + r["abstract"])
    return "\n\n".join(out)


def run_query_architect(user_question):
    llm = get_llm()
    prompt = (
        "You are a biomedical librarian expert in PubMed search strategy.\n"
        "Given this clinical question, generate exactly 5 distinct PubMed search queries using "
        "MeSH terminology and clinical keywords to maximise literature coverage.\n"
        "Return ONLY a numbered list 1-5, one query per line, no explanations.\n\n"
        "Question: " + user_question
    )
    response = llm_invoke_with_retry(llm, prompt)
    raw_lines = response.content.strip().split("\n")
    queries = []
    for line in raw_lines:
        clean = re.sub(r"^[\d]+[\.)\s]+", "", line.strip())
        if clean:
            queries.append(clean)
    return queries[:5]


def run_literature_scout(queries):
    from retrieval.pubmed import fetch_europepmc
    all_papers = {}
    import time
    for q in queries:
        time.sleep(0.4)
        for r in fetch_pubmed(q, max_results=5):
            if r["pmid"] not in all_papers:
                all_papers[r["pmid"]] = r
        time.sleep(0.4)
        for r in fetch_europepmc(q, max_results=3):
            if r["pmid"] not in all_papers:
                all_papers[r["pmid"]] = r
    return all_papers


def run_evidence_synthesiser(user_question, papers):
    llm = get_llm()
    parts = []
    for pmid, p in list(papers.items())[:6]:
        title = p.get("title", "N/A")
        abstract = p["abstract"]
        parts.append("[PMID " + pmid + "]\nTitle: " + title + "\n" + abstract)
    corpus = "\n\n".join(parts)
    prompt = (
        "You are a senior biomedical researcher writing a structured evidence synthesis.\n"
        "Answer the clinical question using ONLY this structure:\n\n"
        "## Background\n"
        "Brief context (2-3 sentences).\n\n"
        "## Key Findings\n"
        "Most important findings with PMID citations inline.\n\n"
        "## Level of Evidence\n"
        "Rate: Strong / Moderate / Preliminary. Justify briefly.\n\n"
        "## Conflicting Evidence\n"
        "Any contradictions across studies.\n\n"
        "## Research Gaps\n"
        "What the literature does not answer.\n\n"
        "## Clinical Implications\n"
        "What this means for practice or future research.\n\n"
        "Clinical Question: " + user_question + "\n\n"
        "Retrieved Literature:\n" + corpus + "\n\n"
        "Be precise and cite PMIDs throughout."
    )
    response = llm_invoke_with_retry(llm, prompt)
    return response.content


def run_citation_builder(papers):
    result_lines = []
    for i, (pmid, p) in enumerate(papers.items(), 1):
        title = p.get("title", "Title unavailable")
        authors = p.get("authors", "Authors unavailable")
        journal = p.get("journal", "Journal unavailable")
        year = p.get("year", "n.d.")
        result_lines.append(
            str(i) + ". " + authors + " (" + year + "). " + title + ". " + journal + ". PMID: " + pmid
        )
    return "\n".join(result_lines)


def run_confidence_scorer(synthesis):
    llm = get_llm()
    prompt = (
        "You are a critical appraiser of biomedical evidence.\n"
        "Given this synthesis, score each section for evidence quality.\n"
        "Return ONLY valid JSON, no markdown, no explanation:\n"
        "{\n"
        '  "Background": {"score": 8, "rationale": "one sentence"},\n'
        '  "Key Findings": {"score": 7, "rationale": "one sentence"},\n'
        '  "Level of Evidence": {"score": 6, "rationale": "one sentence"},\n'
        '  "Conflicting Evidence": {"score": 5, "rationale": "one sentence"},\n'
        '  "Research Gaps": {"score": 7, "rationale": "one sentence"},\n'
        '  "Clinical Implications": {"score": 6, "rationale": "one sentence"}\n'
        "}\n\n"
        "Scores: 8-10 = strong evidence, 5-7 = moderate, 1-4 = weak/preliminary.\n\n"
        "Synthesis:\n" + synthesis
    )
    response = llm_invoke_with_retry(llm, prompt)
    import json
    text = response.content.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def run_selective_review(user_question, selected_papers):
    llm = get_llm()
    parts = []
    for pmid, p in selected_papers.items():
        title = p.get("title", "N/A")
        abstract = p.get("abstract", "")[:400]
        authors = p.get("authors", "")
        year = p.get("year", "")
        parts.append("[PMID " + pmid + "] " + authors + " (" + year + "). " + title + "\n" + abstract)
    corpus = "\n\n".join(parts)
    prompt = (
        "You are an academic writer producing a literature review paragraph.\n"
        "Write a single cohesive academic paragraph (200-300 words) that synthesises "
        "the following selected papers in relation to this question.\n"
        "Cite papers inline by PMID in parentheses e.g. (PMID: 12345678).\n"
        "Write in formal academic prose. No bullet points. No headings.\n\n"
        "Question: " + user_question + "\n\n"
        "Selected Papers:\n" + corpus
    )
    response = llm_invoke_with_retry(llm, prompt)
    return response.content


def run_predictive_model(user_question, synthesis):
    llm = get_llm()
    prompt = (
        "You are a biomedical futurist analyzing research trends.\n"
        "Based on this evidence synthesis, provide two short forecasts:\n\n"
        "## Constructive Forecast\n"
        "2-3 sentences: What directions does the current evidence suggest the field is moving toward? "
        "What findings are likely to be confirmed or expanded in future research?\n\n"
        "## Destructive Forecast\n"
        "2-3 sentences: Which current assumptions, treatments, or paradigms does the evidence suggest "
        "may be challenged, overturned, or significantly revised in coming years?\n\n"
        "IMPORTANT: Always produce both sections even if evidence is limited. Never ask for more input.\n"
        "Be specific and grounded in the evidence. No speculation beyond what the data implies.\n\n"
        "Clinical Question: " + user_question + "\n\n"
        "Synthesis:\n" + synthesis
    )
    response = llm_invoke_with_retry(llm, prompt)
    return response.content


def run_table_extractor(user_question, synthesis, papers):
    llm = get_llm()
    paper_list = []
    for pmid, p in list(papers.items())[:10]:
        authors = p.get("authors", "")
        first_author = authors.split(",")[0].strip() if authors else "Unknown"
        paper_list.append("PMID " + pmid + ": " + first_author + " - " + p.get("title", "N/A") + " (" + p.get("year", "") + ")")
    papers_str = "\n".join(paper_list)
    prompt = (
        "You are a biomedical data extractor.\n"
        "From this synthesis and paper list, extract a comparison table.\n"
        "Return ONLY valid JSON, no markdown, no explanation.\n"
        "Format:\n"
        "{\n"
        '  "title": "Comparison of Methods/Treatments",\n'
        '  "columns": ["Study (PMID)", "Method/Treatment", "Key Metric", "Outcome", "Year"],\n'
        '  "rows": [\n'
        '    ["Smith et al. (PMID: 12345)", "CNN", "Accuracy: 95%", "Positive", "2024"],\n'
        '    ...\n'
        '  ]\n'
        "}\n\n"
        "Rules:\n"
        "- Maximum 8 rows, NO duplicate rows\n"
        "- Each study should appear at most once\n"
        "- Use the actual first author surname from the paper list, never write 'Author'\n"
        "- Only include rows where you have concrete data from the synthesis\n"
        "- If no specific metrics exist, use concise descriptive outcomes\n"
        "- Never invent data\n\n"
        "Clinical Question: " + user_question + "\n\n"
        "Papers:\n" + papers_str + "\n\n"
        "Synthesis:\n" + synthesis[:1500]
    )
    response = llm_invoke_with_retry(llm, prompt)
    import json
    text = response.content.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(text)

def run_prisma_filter(user_question, papers):
    llm = get_llm()
    import json
    paper_list = []
    for pmid, p in papers.items():
        paper_list.append(
            "PMID " + pmid + ": " + p.get("title", "N/A") + "\n" +
            p.get("abstract", "")[:200]
        )
    corpus = "\n\n".join(paper_list)
    prompt = (
        "You are a systematic review methodologist applying PRISMA screening criteria.\n"
        "For each paper, decide if it should be INCLUDED or EXCLUDED for answering this clinical question.\n"
        "Return ONLY valid JSON, no markdown, no explanation.\n"
        "Format:\n"
        "{\n"
        '  "decisions": [\n'
        '    {"pmid": "12345678", "decision": "included", "reason": "one sentence"},\n'
        '    {"pmid": "87654321", "decision": "excluded", "reason": "one sentence"}\n'
        '  ]\n'
        "}\n\n"
        "Inclusion criteria: directly relevant to the clinical question, has empirical data or clinical findings.\n"
        "Exclusion criteria: off-topic, editorial, commentary without data, animal studies if human data exists.\n\n"
        "Clinical Question: " + user_question + "\n\n"
        "Papers:\n" + corpus
    )
    response = llm_invoke_with_retry(llm, prompt)
    text = response.content.strip().replace("```json", "").replace("```", "").strip()
    data = json.loads(text)
    result = {}
    for d in data["decisions"]:
        pmid = d["pmid"]
        if pmid in papers:
            result[pmid] = {
                **papers[pmid],
                "included": d["decision"] == "included",
                "reason": d["reason"]
            }
    for pmid in papers:
        if pmid not in result:
            result[pmid] = {**papers[pmid], "included": True, "reason": "Not reviewed"}
    return result


def run_pipeline(user_question):
    print("[1/4] Query Architect: generating search queries...")
    queries = run_query_architect(user_question)
    print("      Generated " + str(len(queries)) + " queries")
    print("[2/4] Literature Scout: fetching PubMed in parallel...")
    papers = run_literature_scout(queries)
    print("      Retrieved " + str(len(papers)) + " unique papers")
    print("[3/4] Evidence Synthesiser: building structured synthesis...")
    synthesis = run_evidence_synthesiser(user_question, papers)
    print("[4/4] Citation Builder: formatting references...")
    citations = run_citation_builder(papers)
    return {
        "question": user_question,
        "queries": queries,
        "paper_count": len(papers),
        "synthesis": synthesis,
        "citations": citations,
        "papers": papers
    }


def build_agent():
    llm = get_llm()
    return create_react_agent(llm, [PubMedSearch])


if __name__ == "__main__":
    question = "What are the most effective ML methods for epilepsy seizure detection from EEG signals?"
    result = run_pipeline(question)
    print("\n=== SYNTHESIS ===")
    print(result["synthesis"])
    print("\n=== REFERENCES ===")
    print(result["citations"])