import json
import time

try:
    from citation_ghost_detector import get_groq_llm, llm_invoke_with_retry
except ImportError:
    from agent.citation_ghost_detector import get_groq_llm, llm_invoke_with_retry


PROMPT_TEMPLATE = """You are a rigorous cross-paper consistency auditor for biomedical research.
You will be given a finding from Paper A and a finding from Paper B, both addressing the same topic/question.

Decide how the two findings relate to each other.

Categories:
- "consistent": the findings agree — same direction of effect, and any differences in magnitude or population are compatible/complementary rather than conflicting. Also use "consistent" when the two findings simply don't overlap in topic (see rule below) — there is no actual conflict.
- "partial_conflict": the findings are in tension but not flatly opposed — e.g. same direction of effect but substantially different magnitude, one reaches statistical significance and the other doesn't, or the effect holds in one subgroup/setting but not clearly in the other.
- "direct_contradiction": the findings flatly oppose each other — opposite direction of effect on the same outcome in comparable populations, or one confirms an association/mechanism that the other explicitly refutes.

Required rule for "direct_contradiction": it applies ONLY when both papers make a claim about the SAME specific question or metric (e.g. both report the effect of the same intervention on the same outcome, or both assess the predictive accuracy of the same score) and reach opposing conclusions on it. A shared broad topic (e.g. "chest trauma", "thoracic injury") is NOT enough — if the two findings are actually measuring or claiming different things (different metric, different research question, no shared outcome to compare), there is nothing to oppose. In that case flag "consistent" and explain in the explanation that the topics/questions don't overlap, so no real conflict exists. Do not flag "direct_contradiction" just because two papers are about the same general clinical area.

Example of non-overlapping topics that must NOT be flagged as a contradiction:
Paper A finds that a trauma severity score (e.g. STUMBL) outperforms another score (ISS) at predicting ICU admission and mortality after blunt chest trauma. Paper B finds that road traffic collisions and low-height falls are the most common mechanisms of blunt chest trauma in elderly patients. Both papers are about blunt chest trauma, but Paper A is about the predictive accuracy of a scoring tool and Paper B is about injury mechanism/epidemiology — they make no claim about the same question, so this is "consistent" (no overlap, hence no conflict), not "direct_contradiction".

Return ONLY valid JSON, no markdown, no explanation outside the JSON:
{{
  "flag": "consistent" | "partial_conflict" | "direct_contradiction",
  "confidence": <integer 0-100, your confidence in this flag>,
  "explanation": "<one to two sentences, cite the specific point of agreement or conflict>"
}}

Paper A ({paper_a}): {finding_a}

Paper B ({paper_b}): {finding_b}
"""


def check_contradiction(paper_a, finding_a, paper_b, finding_b, llm=None):
    """
    paper_a / paper_b: short labels identifying each paper (e.g. "Smith et al. 2019").
    finding_a / finding_b: the stated finding/claim from each paper on the shared topic.

    Returns: {"flag": str, "confidence": int, "explanation": str}
    """
    llm = llm or get_groq_llm()
    prompt = PROMPT_TEMPLATE.format(paper_a=paper_a, finding_a=finding_a, paper_b=paper_b, finding_b=finding_b)
    response = llm_invoke_with_retry(llm, prompt)
    text = response.content.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    result = json.loads(text)
    if result.get("flag") not in ("consistent", "partial_conflict", "direct_contradiction"):
        raise ValueError(f"Unexpected flag from model: {result.get('flag')!r}")
    result["confidence"] = int(result["confidence"])
    return result


def run_cross_paper_contradiction_finder(pairs):
    """
    pairs: list of {"paper_a": str, "finding_a": str, "paper_b": str, "finding_b": str}
    Returns the same list with "flag", "confidence", "explanation" attached to each item.
    """
    llm = get_groq_llm()
    results = []
    for i, item in enumerate(pairs):
        if i > 0:
            time.sleep(1.5)
        try:
            verdict = check_contradiction(
                item["paper_a"], item["finding_a"], item["paper_b"], item["finding_b"], llm=llm
            )
        except Exception as e:
            verdict = {"flag": "error", "confidence": 0, "explanation": str(e)}
        results.append({**item, **verdict})
    return results


if __name__ == "__main__":
    sample_pairs = [
        {
            # consistent: similar direction and magnitude in similar populations
            "paper_a": "Smith et al., 2018",
            "finding_a": "Statin therapy reduced major cardiovascular events by 25% (HR 0.75) in a randomized trial of 10,000 adults with elevated LDL cholesterol.",
            "paper_b": "Jones et al., 2020",
            "finding_b": "In a separate randomized trial of 8,500 adults with hyperlipidemia, statin therapy reduced major cardiovascular events by 22% (HR 0.78).",
        },
        {
            # partial_conflict: same direction, but magnitude/significance disagree
            "paper_a": "Nguyen et al., 2015",
            "finding_a": "In postmenopausal women, hormone replacement therapy significantly reduced hip fracture risk by 34% (p=0.01) in a 5-year randomized trial.",
            "paper_b": "Patel et al., 2017",
            "finding_b": "In a similarly designed trial of postmenopausal women, hormone replacement therapy was associated with a 10% reduction in hip fracture risk, but this did not reach statistical significance (p=0.22).",
        },
        {
            # direct_contradiction: opposite direction of effect on the same outcome (classic HRT/CHD case)
            "paper_a": "Stampfer et al., 1991 (observational cohort)",
            "finding_a": "Hormone replacement therapy was associated with a 30% reduction in the risk of coronary heart disease in postmenopausal women (observational cohort, n=50,000).",
            "paper_b": "Women's Health Initiative, 2002 (randomized controlled trial)",
            "finding_b": "In a randomized controlled trial of postmenopausal women, hormone replacement therapy significantly increased the risk of coronary heart disease (HR 1.29, 95% CI 1.02-1.63).",
        },
        {
            # regression case: same broad topic (blunt chest trauma) but different question/metric
            # (predictive accuracy of a severity score vs. injury mechanism epidemiology in the elderly)
            # -> must be "consistent" (no overlap), not "direct_contradiction"
            "paper_a": "Isharanto et al., 2026",
            "finding_a": "The STUMBL score outperformed ISS in predicting prolonged hospitalization, ICU admission, and in-hospital mortality among patients with blunt thoracic trauma. Its application may improve early risk stratification and support clinical decision-making in Indonesian tertiary hospitals.",
            "paper_b": "Hefny et al., 2026",
            "finding_b": "Despite reduced occupational exposure and lower engagement in high-risk activities, road traffic collisions remain a major cause of blunt chest trauma in elderly populations. Although many falls are low-energy events, their high incidence makes them a frequent contributor to the overall blunt chest trauma burden in the elderly.",
        },
    ]

    results = run_cross_paper_contradiction_finder(sample_pairs)
    for i, r in enumerate(results, 1):
        print(f"\n--- Sample {i} ---")
        print(f"Paper A ({r['paper_a']}): {r['finding_a'][:100]}...")
        print(f"Paper B ({r['paper_b']}): {r['finding_b'][:100]}...")
        print(f"Flag: {r['flag']} (confidence: {r['confidence']})")
        print(f"Explanation: {r['explanation']}")
