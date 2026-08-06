import os, json, time


def get_groq_llm():
    from langchain_groq import ChatGroq
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set in environment")
    return ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0,
        api_key=key,
    )


def llm_invoke_with_retry(llm, prompt, max_retries=5):
    for attempt in range(max_retries):
        try:
            return llm.invoke(prompt)
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = 10 * (attempt + 1)
                print(f"[CitationGhost] Rate limit hit, waiting {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Max retries exceeded on rate limit")


PROMPT_TEMPLATE = """You are a rigorous citation auditor for biomedical research papers.
You will be given a claim from a paper, the citation attached to it, and the text of the cited source (abstract or excerpt).

Decide whether the cited source actually supports the specific claim it is attached to.

Categories:
- "supported": the source directly and specifically supports the claim as stated.
- "partial": the source is topically related but does not fully substantiate the specific claim (e.g. different population, different outcome measure, weaker or narrower finding than what is claimed).
- "ghost": the source does not support the claim at all (unrelated topic, contradicts the claim, or the claim's specific assertion is absent from the source).

Important distinction — exaggerated magnitude is "partial", not "ghost":
If the source supports the general direction/substance of the claim but the claim overstates the magnitude or strength of the effect, that is "partial", not "ghost". Reserve "ghost" for sources whose substance does not support the claim at all.
Example: Claim states a drug "eliminates cardiovascular risk entirely"; the source reports a measured 14% relative risk reduction, not elimination. The source supports the substance (the drug reduces cardiovascular risk) but not the exaggerated magnitude ("eliminates"/"entirely") — this is "partial".

Return ONLY valid JSON, no markdown, no explanation outside the JSON:
{{
  "flag": "supported" | "partial" | "ghost",
  "confidence": <integer 0-100, your confidence in this flag>,
  "explanation": "<one to two sentences, cite the specific mismatch or match>"
}}

Claim: {claim}

Citation: {citation}

Cited Source Text:
{source_text}
"""


def check_citation(claim, citation, source_text, llm=None):
    """
    claim: the sentence/passage in the paper making the assertion.
    citation: the citation marker/reference attached to the claim (e.g. "[12]" or "Smith et al. 2019").
    source_text: the abstract or excerpt of the source being cited.

    Returns: {"flag": str, "confidence": int, "explanation": str}
    """
    llm = llm or get_groq_llm()
    prompt = PROMPT_TEMPLATE.format(claim=claim, citation=citation, source_text=source_text)
    response = llm_invoke_with_retry(llm, prompt)
    text = response.content.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    result = json.loads(text)
    if result.get("flag") not in ("supported", "partial", "ghost"):
        raise ValueError(f"Unexpected flag from model: {result.get('flag')!r}")
    result["confidence"] = int(result["confidence"])
    return result


def run_citation_ghost_detector(claims):
    """
    claims: list of {"claim": str, "citation": str, "source_text": str}
    Returns the same list with "flag", "confidence", "explanation" attached to each item.
    """
    llm = get_groq_llm()
    results = []
    for i, item in enumerate(claims):
        if i > 0:
            time.sleep(1.5)
        try:
            verdict = check_citation(item["claim"], item["citation"], item["source_text"], llm=llm)
        except Exception as e:
            verdict = {"flag": "error", "confidence": 0, "explanation": str(e)}
        results.append({**item, **verdict})
    return results


if __name__ == "__main__":
    sample_claims = [
        {
            "claim": "Metformin reduces the incidence of type 2 diabetes by 31% in high-risk adults (Knowler et al., 2002).",
            "citation": "Knowler et al., 2002",
            "source_text": "Diabetes Prevention Program Research Group. Reduction in the incidence of type 2 diabetes with lifestyle intervention or metformin. N Engl J Med. 2002. Randomized trial of 3,234 nondiabetic adults with elevated fasting/post-load glucose, assigned to placebo, metformin, or lifestyle intervention. Metformin reduced the incidence of diabetes by 31% compared with placebo; lifestyle intervention reduced incidence by 58%.",
        },
        {
            "claim": "Long-term use of proton pump inhibitors is associated with an increased risk of hip fracture in postmenopausal women (Chen et al., 2015).",
            "citation": "Chen et al., 2015",
            "source_text": "Chen X, et al. Association between vitamin D receptor gene polymorphisms and osteoporosis risk in East Asian populations: a meta-analysis. J Bone Miner Metab. 2015. Meta-analysis of 14 case-control studies examining VDR gene polymorphisms (FokI, BsmI, TaqI) and osteoporosis susceptibility in East Asian cohorts. No mention of proton pump inhibitors, fracture outcomes, or postmenopausal drug exposure.",
        },
        {
            "claim": "SGLT2 inhibitors eliminate cardiovascular risk entirely in patients with type 2 diabetes (Zinman et al., 2015).",
            "citation": "Zinman et al., 2015",
            "source_text": "Zinman B, et al. Empagliflozin, Cardiovascular Outcomes, and Mortality in Type 2 Diabetes. N Engl J Med. 2015. Randomized trial of empagliflozin vs placebo in 7,020 patients with type 2 diabetes and established cardiovascular disease. Empagliflozin reduced the primary composite cardiovascular outcome (14.0% vs 10.5%, relative risk reduction 14%) and cardiovascular death (38% relative risk reduction) over a median 3.1 years follow-up. Risk was reduced, not eliminated.",
        },
    ]

    results = run_citation_ghost_detector(sample_claims)
    for i, r in enumerate(results, 1):
        print(f"\n--- Sample {i} ---")
        print(f"Claim: {r['claim']}")
        print(f"Citation: {r['citation']}")
        print(f"Flag: {r['flag']} (confidence: {r['confidence']})")
        print(f"Explanation: {r['explanation']}")
