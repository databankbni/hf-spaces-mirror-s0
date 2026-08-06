import math

import pytest

from halt_cot import (
    AnswerCandidate,
    EntropyHaltingController,
    HaltCoTConfig,
    answer_distribution_from_scores,
    entropy_from_probabilities,
    integer_candidates,
    multiple_choice_candidates,
    normalize_candidates,
    numeric_candidates_from_texts,
    yes_no_candidates,
)


def test_uniform_binary_entropy_is_one_bit():
    entropy = entropy_from_probabilities({"Yes": 0.5, "No": 0.5}, entropy_unit="bits")
    assert entropy == pytest.approx(1.0)


def test_answer_distribution_uses_softmax_and_argmax():
    distribution = answer_distribution_from_scores({"A": 4.0, "B": 0.0}, entropy_unit="bits")
    assert distribution.prediction == "A"
    assert distribution.probabilities["A"] > 0.98
    assert 0.0 < distribution.entropy < 0.2


def test_entropy_validates_probability_mass():
    with pytest.raises(ValueError, match="sum to 1"):
        entropy_from_probabilities({"A": 0.2, "B": 0.2})


def test_halting_controller_requires_consecutive_low_entropy_steps():
    controller = EntropyHaltingController(
        HaltCoTConfig(theta=0.5, consecutive_low_entropy=2, max_steps=4)
    )
    first = controller.observe(entropy=0.4, step_index=1)
    second = controller.observe(entropy=0.3, step_index=2)
    assert not first.should_halt
    assert second.should_halt
    assert second.low_entropy_streak == 2


def test_halting_controller_respects_min_steps():
    controller = EntropyHaltingController(
        HaltCoTConfig(theta=0.5, min_steps=3, consecutive_low_entropy=1, max_steps=4)
    )
    assert not controller.observe(entropy=0.1, step_index=1).should_halt
    assert not controller.observe(entropy=0.1, step_index=2).should_halt
    assert controller.observe(entropy=0.1, step_index=3).should_halt


def test_candidate_normalization_rejects_duplicates():
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_candidates(["A", "a"])


def test_yes_no_candidates_include_aliases():
    yes, no = yes_no_candidates()
    assert yes.label == "Yes"
    assert "YES" in yes.aliases
    assert no.label == "No"


def test_multiple_choice_candidates_include_common_forms():
    candidates = multiple_choice_candidates(["A", "B"])
    assert candidates[0] == AnswerCandidate("A", aliases=("a", "(A)", "A.", "A)"))
    assert candidates[1].label == "B"


def test_integer_candidates_are_inclusive():
    candidates = integer_candidates(2, 4)
    assert [candidate.label for candidate in candidates] == ["2", "3", "4"]


def test_numeric_candidates_from_texts_extracts_numbers_and_range():
    candidates = numeric_candidates_from_texts(
        ["The answer is 1,234.5", "Then subtract -7."],
        extra_integers=(0, 2),
    )
    labels = [candidate.label for candidate in candidates]
    assert "-7" in labels
    assert "1234.5" in labels
    assert {"0", "1", "2"}.issubset(labels)


def test_config_validation():
    with pytest.raises(ValueError, match="theta"):
        HaltCoTConfig(theta=-math.inf)
