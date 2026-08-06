import json
import time

try:
    from citation_ghost_detector import get_groq_llm, llm_invoke_with_retry
except ImportError:
    from agent.citation_ghost_detector import get_groq_llm, llm_invoke_with_retry


ELEMENTS = (
    "sample_size",
    "statistical_methods",
    "data_availability",
    "code_materials_availability",
    "inclusion_exclusion_criteria",
)


PROMPT_TEMPLATE = """You are a rigorous reproducibility auditor for biomedical research papers.
You will be given a paper's Methodology section.

Check whether each of the following five elements is clearly present in the text. For each, decide present (true) or missing (false), and give a short reason or quote.

1. sample_size: An explicit sample size (n=...) or a clear statement of how many participants/samples were included.
2. statistical_methods: The statistical test(s) or analytical method(s) used are explicitly named (e.g. "t-test", "Cox proportional hazards", "multivariate logistic regression"), not just "data were analyzed".
3. data_availability: A statement about whether/how the underlying data can be accessed (e.g. deposited in a repository, available upon request, or explicitly stated as unavailable).
4. code_materials_availability: A statement about code, software, protocols, or materials being available (e.g. a shared code repository, reagent/protocol availability statement).
5. inclusion_exclusion_criteria: Clear, specific inclusion and/or exclusion criteria for participants/samples, not just a vague population description.

Return ONLY valid JSON, no markdown, no explanation outside the JSON:
{{
  "sample_size": {{"present": true|false, "evidence": "<short quote or reason>"}},
  "statistical_methods": {{"present": true|false, "evidence": "<short quote or reason>"}},
  "data_availability": {{"present": true|false, "evidence": "<short quote or reason>"}},
  "code_materials_availability": {{"present": true|false, "evidence": "<short quote or reason>"}},
  "inclusion_exclusion_criteria": {{"present": true|false, "evidence": "<short quote or reason>"}},
  "explanation": "<one to two sentence overall summary of reproducibility strengths/gaps>"
}}

Methodology Section:
{methodology}
"""


def check_reproducibility(methodology, llm=None):
    """
    methodology: the paper's stated Methods/Methodology section text.

    Returns: {"score": int (0-100), "breakdown": {element: {"present": bool, "evidence": str}, ...}, "explanation": str}
    Score is computed as the percentage of the five elements found present.
    """
    llm = llm or get_groq_llm()
    prompt = PROMPT_TEMPLATE.format(methodology=methodology)
    response = llm_invoke_with_retry(llm, prompt)
    text = response.content.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    result = json.loads(text)

    breakdown = {}
    for element in ELEMENTS:
        entry = result.get(element)
        if not isinstance(entry, dict) or "present" not in entry:
            raise ValueError(f"Missing or malformed element in model response: {element!r}")
        breakdown[element] = {"present": bool(entry["present"]), "evidence": entry.get("evidence", "")}

    found_count = sum(1 for entry in breakdown.values() if entry["present"])
    score = round(found_count / len(ELEMENTS) * 100)

    return {"score": score, "breakdown": breakdown, "explanation": result.get("explanation", "")}


def run_reproducibility_score(papers):
    """
    papers: list of {"methodology": str}
    Returns the same list with "score", "breakdown", "explanation" attached to each item.
    """
    llm = get_groq_llm()
    results = []
    for i, item in enumerate(papers):
        if i > 0:
            time.sleep(1.5)
        try:
            verdict = check_reproducibility(item["methodology"], llm=llm)
        except Exception as e:
            verdict = {"score": 0, "breakdown": {}, "explanation": f"Error: {e}"}
        results.append({**item, **verdict})
    return results


if __name__ == "__main__":
    sample_papers = [
        {
            # high reproducibility: all five elements present
            "methodology": (
                "We enrolled 342 patients (n=342) meeting the following inclusion criteria: age 18-75, "
                "confirmed diagnosis of type 2 diabetes for at least 1 year, and HbA1c between 7.5-10.5%. "
                "Exclusion criteria included pregnancy, eGFR <30 mL/min, and prior use of the study drug class. "
                "Statistical analysis was performed using multivariate logistic regression and Cox proportional "
                "hazards models in R version 4.2. All data supporting the findings of this study are available "
                "in the public repository (doi:10.5281/zenodo.123456). Analysis code is available at "
                "github.com/example/study-code."
            ),
        },
        {
            # low reproducibility: none of the five elements clearly present
            "methodology": (
                "Patients with diabetes were recruited from local clinics and followed for six months to assess "
                "changes in blood sugar control. Data were analyzed and results are presented below."
            ),
        },
        {
            # medium reproducibility: sample size and stats named, but no availability statements and vague criteria
            "methodology": (
                "A total of 150 participants with rheumatoid arthritis were enrolled. Statistical comparisons "
                "between groups were performed using the Mann-Whitney U test and chi-square test where "
                "appropriate. Participants were required to have an established diagnosis of rheumatoid arthritis."
            ),
        },
    ]

    results = run_reproducibility_score(sample_papers)
    for i, r in enumerate(results, 1):
        print(f"\n--- Sample {i} ---")
        print(f"Methodology: {r['methodology'][:100]}...")
        print(f"Score: {r['score']}")
        for element, entry in r["breakdown"].items():
            status = "FOUND" if entry["present"] else "MISSING"
            print(f"  [{status}] {element}: {entry['evidence']}")
        print(f"Explanation: {r['explanation']}")
