import re


DOMAIN_ALIASES = {
    "formal education": "formalno_obrazovanje",
    "formalno obrazovanje": "formalno_obrazovanje",
    "formalno_obrazovanje": "formalno_obrazovanje",
    "formal": "formalno_obrazovanje",
    "etf": "formalno_obrazovanje",

    "informal education": "neformalno_obrazovanje",
    "neformalno obrazovanje": "neformalno_obrazovanje",
    "neformalno_obrazovanje": "neformalno_obrazovanje",
    "informal": "neformalno_obrazovanje",
    "jovan os": "neformalno_obrazovanje",

    "sport": "sport",
    "trening": "sport",

    "career": "karijera",
    "karijera": "karijera",
}


def normalize_domain(domain: str) -> str:
    key = domain.strip().lower()
    return DOMAIN_ALIASES.get(key, key)


def weights_to_dict(weights):
    """
    Expected DB format:
    [('formalno_obrazovanje', 30), ('neformalno_obrazovanje', 25), ...]
    """
    return {normalize_domain(domain): float(weight) for domain, weight in weights}


def domain_scores_to_dict(domain_scores):
    """
    Expected EvaluationOutput.domain_scores:
    [DomainScore(domain='Formal Education', score=7.5, reason='...'), ...]
    """
    result = {}

    for item in domain_scores:
        domain = normalize_domain(item.domain)
        result[domain] = float(item.score)

    return result


def calculate_weighted_overall(evaluation, weights, plan_weight=0.2):
    """
    Calculates final score using:
    - domain scores from LLM
    - domain weights from DB
    - plan completion score from LLM

    final = 80% weighted domain score + 20% plan completion score
    """

    weights_dict = weights_to_dict(weights)
    scores_dict = domain_scores_to_dict(evaluation.domain_scores)

    weighted_sum = 0.0
    used_weight = 0.0

    for domain, weight in weights_dict.items():
        if domain in scores_dict:
            weighted_sum += scores_dict[domain] * weight
            used_weight += weight

    if used_weight == 0:
        weighted_domain_score = float(evaluation.overall_score)
    else:
        weighted_domain_score = weighted_sum / used_weight

    plan_completion_score = float(evaluation.plan_completion_score)

    domain_weight = 1.0 - plan_weight
    final_score = (
        domain_weight * weighted_domain_score
        + plan_weight * plan_completion_score
    )

    return round(final_score, 1)


##def update_markdown_overall_score(markdown: str, weighted_score: float, llm_score: float) -> str:
    """
    Replaces the Overall Score in markdown and adds a note that Python calculated it.
    """

    pattern = r"(## Overall Score\s*\n)([0-9]+(?:\.[0-9]+)?/10)"

    replacement = (
        f"## Overall Score\n"
        f"{weighted_score}/10\n\n"
        f"_Python weighted score. LLM initial estimate: {llm_score}/10._"
    )

    updated = re.sub(pattern, replacement, markdown, count=1)

    return updated

def update_markdown_overall_score(
    markdown: str,
    weighted_score: float,
    llm_score: float,
) -> str:
    pattern = r"(## Overall Score\s*\n)\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*10"
    replacement = (
        f"## Overall Score\n"
        f"{weighted_score}/10\n\n"
        f"_Python weighted score. LLM initial estimate: {llm_score}/10._"
    )

    updated, n = re.subn(pattern, replacement, markdown, count=1)

    if n == 0:
        return (
            f"## Overall Score\n"
            f"{weighted_score}/10\n\n"
            f"_Python weighted score. LLM initial estimate: {llm_score}/10._\n\n"
            f"{markdown}"
        )

    return updated