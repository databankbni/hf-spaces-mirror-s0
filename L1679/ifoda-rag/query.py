"""
Query interface for IFODA RAG. Structured answers with citations.
"""
import os, re
from typing import List, Optional
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()  # load OPENAI_API_KEY etc. from a local .env if present
except ImportError:
    pass

from retriever import HybridRetriever, RetrievedChunk
from config import *

# Section/table headers that leak into product_name during chunking.
# These are NOT real products and must not be shown to the user.
_NON_PRODUCT_NAMES = {
    "general", "unknown", "n/a", "технология", "культура", "заболевание",
    "норма расхода", "кратность", "опрыскивание растений", "регистрационные",
    "harmful", "application", "culture", "hazard", "dosage", "regulations",
    "last treatment before", "spraying of plants", "spraying of plants during the",
    "period and method of", "insecticide", "fungicide", "herbicide", "fertilizer",
    "using in early spring before", "хлопчатник", "зерно", "пшеница", "рис",
    "колорадский", "cotton", "wheat", "rice", "corn", "apple", "grape",
    "tomato", "potato", "onion",
}

# Prefixes that signal a table/section header rather than a product name.
_HEADER_PREFIXES = (
    "обработка", "опрыскивание", "применение", "внесение", "пшеница ",
    "культура", "норма", "spraying", "using", "last", "period", "application",
    "etching", "treatment", "culture", "highly", "effective", "this ", "it ",
)

def _clean_product_name(name: str) -> Optional[str]:
    """Return a displayable product name, or None if it is a header/noise."""
    if not name:
        return None
    norm = name.strip().lower().rstrip(":")
    if norm in _NON_PRODUCT_NAMES:
        return None
    # Must contain letters and be reasonably sized to be a real product name
    if len(norm) < 3 or not re.search(r"[a-zа-яё]", norm):
        return None
    # Drop sentence-like section headers (long phrases that start with a header word)
    if norm.startswith(_HEADER_PREFIXES) and len(norm.split()) >= 2:
        return None
    # Real product names are short; long phrases are descriptions/headers, not names
    if len(norm.split()) > 8:
        return None
    return name.strip()

@dataclass
class Answer:
    query: str; answer: str; citations: List[dict]
    products_found: List[str]; confidence: str

SYSTEM_PROMPT_RU = """Ты — эксперт-агроном компании IFODA (Узбекско-Японское СП).
Давай точные рекомендации СТРОГО на основе предоставленного контекста.

ПРАВИЛА:
1. Отвечай только по документам. НЕ выдумывай дозировки.
2. Указывай ТОЧНЫЕ нормы расхода (л/га, кг/га, г/га).
3. Указывай культуру, вредный объект, срок ожидания, кратность.
4. ВСЕГДА цитируй источник в скобках [1], [2]...
5. Если информации недостаточно — ЧЕСТНО скажи об этом.
6. Предупреждай о мерах безопасности, если применимо.
Если запрос не связан с продуктами IFODA — вежливо откажись."""

SYSTEM_PROMPT_EN = """You are an IFODA agronomist expert (Uzbek-Japanese JV).
Provide precise recommendations STRICTLY from the provided context.

RULES:
1. Answer only from the documents. Do NOT invent dosages.
2. Provide EXACT dosages (l/ha, kg/ha, g/ha).
3. Specify crop, pest/disease, waiting period, treatment frequency.
4. ALWAYS cite sources in square brackets [1], [2]...
5. If information is insufficient — HONESTLY say so.
6. Warn about safety measures when applicable.
If the query is unrelated to IFODA products — politely decline."""


class IFODAQueryEngine:
    def __init__(self, use_llm: bool = False):
        self.retriever = HybridRetriever()
        self.use_llm = use_llm
        self.llm = None
        self.llm_model = None
        if use_llm:
            self._init_llm()

    def _init_llm(self):
        """Initialize an OpenAI-compatible LLM client if an API key is available."""
        try:
            from openai import OpenAI
        except ImportError:
            print("[QUERY] openai not installed. Using context-only mode.")
            self.use_llm = False
            return
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            print("[QUERY] No OPENAI_API_KEY found. Using context-only mode.")
            self.use_llm = False
            return
        api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.llm = OpenAI(api_key=api_key, base_url=api_base)
        self.llm_model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        print(f"[QUERY] LLM initialized: {self.llm_model}")

    def detect_language(self, query: str) -> str:
        return "ru" if len(re.findall(r'[а-яёА-ЯЁ]', query)) > len(query)*0.1 else "en"

    def _generate_llm_answer(self, query: str, results: List[RetrievedChunk], lang: str) -> Optional[str]:
        """Generate a grounded answer via LLM. Returns None on failure (caller falls back)."""
        context = self.retriever.get_context_for_llm(results)
        system_prompt = SYSTEM_PROMPT_RU if lang == "ru" else SYSTEM_PROMPT_EN
        user_msg = (f"Контекст:\n\n{context}\n\nВопрос: {query}" if lang == "ru"
                    else f"Context:\n\n{context}\n\nQuestion: {query}")
        try:
            resp = self.llm.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_msg}],
                temperature=0.1,  # low temperature: factual accuracy is critical
                max_tokens=1500)
            return resp.choices[0].message.content
        except Exception as e:
            print(f"[QUERY] LLM error: {e}. Falling back to context-only answer.")
            return None

    def query(self, query: str, top_k: int = TOP_K_RERANK, use_llm: Optional[bool] = None) -> Answer:
        # Per-request override of self.use_llm. None means "use engine default".
        effective_use_llm = self.use_llm if use_llm is None else use_llm
        lang = self.detect_language(query)
        results = self.retriever.retrieve(query, top_k=top_k)
        if not results:
            return Answer(query=query,
                answer="Информация не найдена в базе знаний IFODA." if lang=="ru" else "No info found in IFODA KB.",
                citations=[], products_found=[], confidence="low")

        # Extract products and dosages
        products = []
        dosages = []
        for r in results:
            pn = _clean_product_name(r.metadata.get("product_name",""))
            if pn and pn not in products:
                products.append(pn)
            dos = re.findall(r'(\d+[.,]?\d*\s*[-–]\s*\d+[.,]?\d*\s*(?:l/ha|kg/ha|g/ha|л/га|кг/га|г/га))', r.text, re.I)
            dosages.extend(dos)
        dosages = list(dict.fromkeys(dosages))  # dedup, keep order

        # Build answer context
        context_parts = []
        citations = []
        for i, r in enumerate(results[:TOP_K_RERANK]):
            if r.score < 0.1: continue
            src = r.metadata.get("source","?"); prod = r.metadata.get("product_name","N/A")
            citations.append({"source":src, "product":prod, "score":round(r.score,4), "index":i+1})
            context_parts.append(f"[{i+1}] {src} | Product: {prod} | Score: {r.score:.3f}\n{r.text[:600]}")
        ctx = "\n\n".join(context_parts)
        conf = "high" if results[0].score > 0.5 else ("medium" if results[0].score > 0.2 else "low")

        # LLM-generated grounded answer (if enabled and reachable)
        if effective_use_llm:
            # Lazy-init the LLM client on first request that needs it.
            if self.llm is None:
                self._init_llm()
            if self.llm is not None:
                llm_ans = self._generate_llm_answer(query, results, lang)
                if llm_ans:
                    return Answer(query=query, answer=llm_ans, citations=citations,
                                  products_found=products[:10], confidence=conf)

        if lang == "ru":
            ans = f"🔍 Результаты по запросу: «{query}»\n\n📋 Найдено продуктов: {', '.join(products[:5]) if products else 'уточните запрос'}\n"
            if dosages: ans += f"📏 Дозировки: {', '.join(dosages[:5])}\n"
            ans += f"\n📄 Источники:\n{ctx}\n\n⚠️ Ответ без LLM. Для генерации подключите OpenAI API."
        else:
            ans = f"🔍 Results for: «{query}»\n\n📋 Products found: {', '.join(products[:5]) if products else 'refine query'}\n"
            if dosages: ans += f"📏 Dosages: {', '.join(dosages[:5])}\n"
            ans += f"\n📄 Sources:\n{ctx}\n\n⚠️ No LLM mode. Connect OpenAI API for generation."

        return Answer(query=query, answer=ans, citations=citations, products_found=products[:10], confidence=conf)

    def get_context_only(self, query: str, top_k: int = TOP_K_RERANK) -> str:
        results = self.retriever.retrieve(query, top_k=top_k)
        return self.retriever.get_context_for_llm(results)

def interactive_cli():
    print("="*60); print("  IFODA RAG System — Knowledge Base Query"); print("  Узбекско-Японское СП «Ifoda Agro Kimyo Himoya»"); print("="*60)
    print("  /en (English)  /ru (русский)  /exit"); print("="*60)
    engine = IFODAQueryEngine(); lang = "ru"
    while True:
        try: q = input(f"\n{'🔍 Вопрос > ' if lang=='ru' else '🔍 Query > '}").strip()
        except (EOFError,KeyboardInterrupt): print("\nДо свидания!"); break
        if not q: continue
        if q=="/en": lang="en"; print("[English]"); continue
        if q=="/ru": lang="ru"; print("[Русский]"); continue
        if q=="/exit": print("До свидания!"); break
        a = engine.query(q)
        print(f"\n📋 ОТВЕТ (confidence: {a.confidence}):"); print("-"*40)
        print(a.answer); print("-"*40)
        if a.citations:
            print(f"\n📎 Источники:")
            for c in a.citations: print(f"  [{c['index']}] {c['source']} | {c['product']} | {c['score']}")

if __name__ == "__main__":
    interactive_cli()
