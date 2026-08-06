import json
import time

try:
    from citation_ghost_detector import get_groq_llm, llm_invoke_with_retry
except ImportError:
    from agent.citation_ghost_detector import get_groq_llm, llm_invoke_with_retry


PROMPT_TEMPLATE = """You are a rigorous methodology auditor for biomedical research papers.
You will be given a paper's stated Methodology section and its Results section.

Decide whether the results are consistent with what the methodology claims to have done.

Look for drift such as:
- Study design mismatch (e.g. methodology claims a randomized controlled trial but results describe no control group or no randomization).
- Sample size mismatch (e.g. methodology states n=200 but results analyze a different, unexplained sample size).
- Outcome measures, assessment methods (e.g. blinding), or analyses described in results that were never mentioned in the methodology, or that contradict it.
- Population/inclusion criteria in results that differ from what methodology specified.

Categories:
- "consistent": results align with what the methodology describes; any differences are explained (e.g. stated dropouts/exclusions) or trivial.
- "minor_drift": there is a real discrepancy between methodology and results, but it does not undermine the core validity of the study (e.g. an unmentioned deviation in assessment procedure, a small unexplained sample size difference).
- "major_drift": there is a substantial mismatch that undermines the validity or interpretation of the results (e.g. claimed RCT with no evident control/randomization in results, large unexplained sample size change, primary outcome measure in results absent from methodology).

Return ONLY valid JSON, no markdown, no explanation outside the JSON:
{{
  "flag": "consistent" | "minor_drift" | "major_drift",
  "confidence": <integer 0-100, your confidence in this flag>,
  "explanation": "<one to two sentences, cite the specific mismatch or confirmation>"
}}

Methodology Section:
{methodology}

Results Section:
{results}
"""


def check_methodology_drift(methodology, results, llm=None):
    """
    methodology: the paper's stated Methods/Methodology section text.
    results: the paper's Results section text.

    Returns: {"flag": str, "confidence": int, "explanation": str}
    """
    llm = llm or get_groq_llm()
    prompt = PROMPT_TEMPLATE.format(methodology=methodology, results=results)
    response = llm_invoke_with_retry(llm, prompt)
    text = response.content.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    result = json.loads(text)
    if result.get("flag") not in ("consistent", "minor_drift", "major_drift"):
        raise ValueError(f"Unexpected flag from model: {result.get('flag')!r}")
    result["confidence"] = int(result["confidence"])
    return result


def run_methodology_drift_tracker(papers):
    """
    papers: list of {"methodology": str, "results": str}
    Returns the same list with "flag", "confidence", "explanation" attached to each item.
    """
    llm = get_groq_llm()
    results_out = []
    for i, item in enumerate(papers):
        if i > 0:
            time.sleep(1.5)
        try:
            verdict = check_methodology_drift(item["methodology"], item["results"], llm=llm)
        except Exception as e:
            verdict = {"flag": "error", "confidence": 0, "explanation": str(e)}
        results_out.append({**item, **verdict})
    return results_out


if __name__ == "__main__":
    sample_papers = [
        {
            # consistent: RCT as described, minor explained attrition
            "methodology": "We conducted a randomized, double-blind, placebo-controlled trial. 200 adults with type 2 diabetes were randomized 1:1 to receive either Drug X or placebo for 24 weeks. The primary outcome was change in HbA1c from baseline to week 24.",
            "results": "Of the 200 randomized participants (100 Drug X, 100 placebo), 194 completed the study; 6 withdrew for reasons unrelated to treatment. Drug X reduced HbA1c by 1.2% versus 0.3% with placebo (p<0.001).",
        },
        {
            # major_drift: RCT claimed, no control group anywhere in results
            "methodology": "We conducted a randomized controlled trial. 150 patients with hypertension were randomized to receive either a lifestyle coaching intervention or standard-care control for 12 months, with blood pressure measured at baseline and endpoint.",
            "results": "All 150 patients received the lifestyle coaching intervention. Mean systolic blood pressure decreased from 148 mmHg to 132 mmHg over 12 months (p<0.001).",
        },
        {
            # minor_drift: sample size and design match, but blinding described in methodology is contradicted in results
            "methodology": "This was a prospective cohort study of 120 patients with rheumatoid arthritis, followed for 12 months. The primary outcome was change in DAS28 score at 12 months, assessed by raters blinded to prior scores.",
            "results": "120 patients were enrolled and followed for 12 months. At 12 months, mean DAS28 score decreased from 5.4 to 3.1 (p<0.001). Assessments were performed by each patient's treating rheumatologist.",
        },
    ]

    results = run_methodology_drift_tracker(sample_papers)
    for i, r in enumerate(results, 1):
        print(f"\n--- Sample {i} ---")
        print(f"Methodology: {r['methodology'][:100]}...")
        print(f"Results: {r['results'][:100]}...")
        print(f"Flag: {r['flag']} (confidence: {r['confidence']})")
        print(f"Explanation: {r['explanation']}")
