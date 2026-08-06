import json
import time

try:
    from citation_ghost_detector import get_groq_llm, llm_invoke_with_retry
except ImportError:
    from agent.citation_ghost_detector import get_groq_llm, llm_invoke_with_retry


PROMPT_TEMPLATE = """You are a rigorous calibration auditor for biomedical research papers.
You will be given a paper's stated claim (its conclusion) and the actual data/results backing that claim.

Decide whether the certainty and strength of the language used in the claim matches the certainty and strength of the evidence.

Look for calibration issues such as:
- Causal language ("proves", "demonstrates", "causes") used for correlational, observational, or associational data where causation cannot be established.
- Absolute or universal language ("always", "completely", "eliminates") used for a partial, modest, or non-significant effect.
- Strong conclusions drawn from small, underpowered, non-significant, or pilot-stage data.
- Conversely, excessively hedged or tentative language ("may possibly suggest a potential link") used to describe a large, statistically robust effect from a well-powered, well-designed study — this undersells solid evidence.

Categories:
- "calibrated": the strength/certainty of the language matches the strength/certainty of the evidence.
- "overstated": the language claims more certainty, causality, or strength than the data supports.
- "understated": the language is more hedged or tentative than the strength of evidence actually supports.

Return ONLY valid JSON, no markdown, no explanation outside the JSON:
{{
  "flag": "calibrated" | "overstated" | "understated",
  "confidence": <integer 0-100, your confidence in this flag>,
  "explanation": "<one to two sentences, cite the specific mismatch or match between language and evidence>"
}}

Claim: {claim}

Data/Results: {data}
"""


def check_calibration(claim, data, llm=None):
    """
    claim: the paper's stated conclusion, as written.
    data: the actual data/results section supporting the claim.

    Returns: {"flag": str, "confidence": int, "explanation": str}
    """
    llm = llm or get_groq_llm()
    prompt = PROMPT_TEMPLATE.format(claim=claim, data=data)
    response = llm_invoke_with_retry(llm, prompt)
    text = response.content.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    result = json.loads(text)
    if result.get("flag") not in ("calibrated", "overstated", "understated"):
        raise ValueError(f"Unexpected flag from model: {result.get('flag')!r}")
    result["confidence"] = int(result["confidence"])
    return result


def run_confidence_calibration_check(items):
    """
    items: list of {"claim": str, "data": str}
    Returns the same list with "flag", "confidence", "explanation" attached to each item.
    """
    llm = get_groq_llm()
    results = []
    for i, item in enumerate(items):
        if i > 0:
            time.sleep(1.5)
        try:
            verdict = check_calibration(item["claim"], item["data"], llm=llm)
        except Exception as e:
            verdict = {"flag": "error", "confidence": 0, "explanation": str(e)}
        results.append({**item, **verdict})
    return results


if __name__ == "__main__":
    sample_items = [
        {
            # overstated: causal/"proves" language for an adjusted observational study
            "claim": "This study proves that coffee consumption causes reduced risk of Parkinson's disease.",
            "data": "In this prospective cohort study of 40,000 adults, higher coffee consumption was associated with a 25% lower risk of Parkinson's disease (HR 0.75, 95% CI 0.65-0.86) after adjusting for age, smoking, and physical activity. Residual confounding cannot be excluded.",
        },
        {
            # calibrated: hedged language matches a small, non-significant pilot result
            "claim": "These findings suggest that Drug X may modestly reduce the risk of hospitalization in patients with heart failure, though further trials are needed to confirm this effect.",
            "data": "In this single-center, open-label pilot study of 45 patients, Drug X was associated with a 12% reduction in hospitalization rate over 6 months, which did not reach statistical significance (p=0.08).",
        },
        {
            # understated: excessive hedging for a large, highly significant RCT effect
            "claim": "These results may possibly indicate a potential link between the vaccine and reduced infection risk.",
            "data": "In a large multi-center randomized controlled trial of 30,000 participants, vaccine recipients had a 94% relative risk reduction in symptomatic infection compared to placebo (95% CI 90-97%, p<0.0001).",
        },
    ]

    results = run_confidence_calibration_check(sample_items)
    for i, r in enumerate(results, 1):
        print(f"\n--- Sample {i} ---")
        print(f"Claim: {r['claim']}")
        print(f"Data: {r['data'][:100]}...")
        print(f"Flag: {r['flag']} (confidence: {r['confidence']})")
        print(f"Explanation: {r['explanation']}")
