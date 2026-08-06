from underdog_lab.scenarios.adjustments import apply_extraction
from underdog_lab.scenarios.schemas import ScenarioExtraction
from underdog_lab.ui.components import factors_html


def test_fallback_is_visible_in_rendered_output(neutral_match):
    extraction = ScenarioExtraction(unsupported_claims=["unrecognized"])
    result = apply_extraction(neutral_match, extraction)
    rendered = factors_html(
        extraction,
        result,
        backend="deterministic fallback",
        backend_error="RuntimeError: model could not load",
    )
    assert "Extracted by deterministic fallback" in rendered
    assert "RuntimeError: model could not load" in rendered
