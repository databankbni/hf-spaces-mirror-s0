from __future__ import annotations

import json
from datetime import date

from underdog_lab.domain import MatchRecord
from underdog_lab.scenarios.prompts import (
    SYSTEM_PROMPT,
    build_messages,
    build_prompt,
    user_content,
)


# ── Mirror of training-side format_example for testing ────────────────


def _training_format(
    home_team: str,
    away_team: str,
    scenario: str,
    expected: dict,
    chat_template_fn,
) -> str:
    """Replicate the Modal training format_example logic for testing."""
    neutral_venue = True
    assistant_json = json.dumps(expected, ensure_ascii=True, sort_keys=True)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": user_content(
                home_team=home_team,
                away_team=away_team,
                text=scenario,
                neutral_venue=neutral_venue,
            ),
        },
        {"role": "assistant", "content": assistant_json},
    ]
    return chat_template_fn(messages)


def _smollm2_chat_template(messages: list[dict[str, str]]) -> str:
    """SmolLM2 ChatML format — mirrors the GGUF internal template."""
    parts = []
    for msg in messages:
        parts.append(f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>")
    return "\n".join(parts)


# ── Tests ─────────────────────────────────────────────────────────────


def test_system_prompt_is_non_empty():
    assert len(SYSTEM_PROMPT) > 50
    assert "factor taxonomy" in SYSTEM_PROMPT


def test_user_content_from_match_and_kwargs_match():
    """user_content() must produce identical output from MatchRecord and kwargs."""
    match = MatchRecord(
        match_id="test",
        kickoff_date=date(2026, 1, 1),
        competition="Test",
        stage="Test",
        home_team="Canada",
        away_team="Mexico",
        venue="Test",
        neutral_venue=True,
        home_goals=0,
        away_goals=0,
        pre_match_home_elo=1800,
        pre_match_away_elo=1800,
        lambda_home=1.18,
        lambda_away=1.18,
        context="test",
    )
    from_match = user_content(match=match, text="The striker is out.")
    from_kwargs = user_content(
        home_team="Canada",
        away_team="Mexico",
        text="The striker is out.",
        neutral_venue=True,
    )
    assert from_match == from_kwargs
    assert "Home team: Canada" in from_match
    assert "Away team: Mexico" in from_match
    assert "Recorded venue: neutral" in from_match
    assert "Scenario: The striker is out." in from_match


def test_build_messages_produces_correct_roles():
    match = MatchRecord(
        match_id="test",
        kickoff_date=date(2026, 1, 1),
        competition="Test",
        stage="Test",
        home_team="Canada",
        away_team="Mexico",
        venue="Test",
        neutral_venue=True,
        home_goals=0,
        away_goals=0,
        pre_match_home_elo=1800,
        pre_match_away_elo=1800,
        lambda_home=1.18,
        lambda_away=1.18,
        context="test",
    )
    messages = build_messages("The striker is out.", match)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "Home team:" in messages[1]["content"]
    assert "Scenario:" in messages[1]["content"]


def test_training_chat_template_matches_runtime_messages():
    """Training format must produce the same system+user prefix as runtime.

    The runtime uses llama.cpp create_chat_completion which applies the GGUF's
    chat template to messages. Training must apply the same template and the
    resulting text must contain the runtime messages as a prefix.
    """
    match = MatchRecord(
        match_id="test",
        kickoff_date=date(2026, 1, 1),
        competition="Test",
        stage="Test",
        home_team="Canada",
        away_team="Mexico",
        venue="Test",
        neutral_venue=True,
        home_goals=0,
        away_goals=0,
        pre_match_home_elo=1800,
        pre_match_away_elo=1800,
        lambda_home=1.18,
        lambda_away=1.18,
        context="test",
    )
    scenario = "Mexico's striker is confirmed out."
    expected = {
        "factors": [
            {
                "factor_type": "key_attacker_unavailable",
                "team": "away",
                "severity": 1.0,
                "certainty": 1.0,
                "evidence": "Mexico's striker is confirmed out.",
            }
        ],
        "unsupported_claims": [],
        "ambiguities": [],
    }

    # Training-side formatted text
    training_text = _training_format(
        match.home_team,
        match.away_team,
        scenario,
        expected,
        _smollm2_chat_template,
    )

    # Runtime-side: what create_chat_completion would produce
    # The GGUF's internal chat template formats messages the same way
    runtime_messages = build_messages(scenario, match)
    runtime_prefix = _smollm2_chat_template(runtime_messages)

    # Training text must start with the runtime prefix (system + user)
    assert training_text.startswith(
        runtime_prefix
    ), f"Training text does not start with runtime prefix.\nTraining: {training_text[:200]}\nRuntime: {runtime_prefix[:200]}"

    # Assistant JSON must be the only part after the prefix
    suffix = training_text[len(runtime_prefix):]
    expected_suffix = (
        f"\n<|im_start|>assistant\n"
        f"{json.dumps(expected, ensure_ascii=True, sort_keys=True)}"
        f"<|im_end|>"
    )
    assert suffix == expected_suffix, (
        f"Training suffix mismatch.\nGot: {repr(suffix)}\nExpected: {repr(expected_suffix)}"
    )


def test_training_inlined_prompts_match_runtime():
    """The inlined SYSTEM_PROMPT and user_content in modal_train.py
    must match the canonical definitions in prompts.py exactly."""
    import ast
    import importlib.util
    import re
    from pathlib import Path

    # Parse modal_train.py to extract the inlined SYSTEM_PROMPT
    train_path = Path("training/modal_train.py")
    source = train_path.read_text()

    # Extract the SYSTEM_PROMPT string using AST
    tree = ast.parse(source)
    train_prompt = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "SYSTEM_PROMPT":
                # Evaluate the constant expression
                train_prompt = eval(compile(ast.Expression(node.value), "<test>", "eval"))
                break

    assert train_prompt is not None, "Could not find SYSTEM_PROMPT in modal_train.py"
    assert train_prompt == SYSTEM_PROMPT, (
        "modal_train.py SYSTEM_PROMPT differs from prompts.py SYSTEM_PROMPT.\n"
        f"Training: {repr(train_prompt[:120])}...\n"
        f"Runtime:  {repr(SYSTEM_PROMPT[:120])}..."
    )

    # Verify user_content produces identical output for same inputs
    # Import the training version dynamically
    spec = importlib.util.spec_from_file_location(
        "modal_train", train_path,
        submodule_search_locations=[str(train_path.parent)]
    )
    # Avoid side effects: just verify the user_content function
    # Parse user_content from the module without executing modal imports
    train_user_content = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "user_content":
            # Compile and evaluate the function
            code = compile(
                ast.Module(body=[node], type_ignores=[]),
                "<test>", "exec"
            )
            ns = {}
            exec(code, ns)
            train_user_content = ns["user_content"]
            break

    assert train_user_content is not None, "Could not find user_content in modal_train.py"

    # Test identical output
    rt = user_content(home_team="Canada", away_team="Mexico", text="Test.", neutral_venue=True)
    tr = train_user_content(home_team="Canada", away_team="Mexico", text="Test.", neutral_venue=True)
    assert rt == tr, f"user_content mismatch:\nRuntime:  {repr(rt)}\nTraining: {repr(tr)}"

    rt_home = user_content(home_team="Canada", away_team="Mexico", text="Test.", neutral_venue=False)
    tr_home = train_user_content(home_team="Canada", away_team="Mexico", text="Test.", neutral_venue=False)
    assert rt_home == tr_home, f"user_content mismatch (home venue)"


def test_user_content_home_venue():
    content = user_content(
        home_team="Argentina",
        away_team="Brazil",
        text="Test scenario.",
        neutral_venue=False,
    )
    assert "Recorded venue: home venue" in content


def test_build_prompt_includes_json_suffix():
    match = MatchRecord(
        match_id="test",
        kickoff_date=date(2026, 1, 1),
        competition="Test",
        stage="Test",
        home_team="Canada",
        away_team="Mexico",
        venue="Test",
        neutral_venue=True,
        home_goals=0,
        away_goals=0,
        pre_match_home_elo=1800,
        pre_match_away_elo=1800,
        lambda_home=1.18,
        lambda_away=1.18,
        context="test",
    )
    raw = build_prompt("The striker is out.", match)
    assert raw.endswith("\nJSON:")
    assert SYSTEM_PROMPT in raw
