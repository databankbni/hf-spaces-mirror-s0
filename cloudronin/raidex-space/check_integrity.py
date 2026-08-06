"""Step-0 data-integrity guard for the Raidex board.

Run in the deploy workflow (and locally) BEFORE shipping. Exits non-zero — failing
the build — if any board model has no mapped developer, if the leaderboard rank is
not RAI-descending, or if the hand-authored Key Findings table has drifted from the
live board. Raidex's premise is independent, accurate scoring; a visible attribution
or rank error discredits the index, so this gate must pass before distribution.

The Developer column is DERIVED from the model name here (the single source of truth),
NOT from the serving provider stored in each result JSON — SambaNova/HF-hosted models
(Llama, DeepSeek, Qwen, Gemma, gpt-oss, MiniMax...) were otherwise mis-attributed to
their host instead of their true developer.
"""
import json
import os
import re
import sys

# Ordered (model-name substring -> developer); first match wins. Add a family here when a
# new one joins the board — the guard below fails loudly on anything unmapped.
DEVELOPER_RULES = [
    ("claude", "Anthropic"),
    ("gpt-oss", "OpenAI"), ("gpt", "OpenAI"), ("o1-", "OpenAI"), ("o3-", "OpenAI"),
    ("gemini", "Google"), ("gemma", "Google"),
    ("llama", "Meta"),
    ("qwen", "Alibaba"),
    ("deepseek", "DeepSeek"),
    ("grok", "xAI"),
    ("minimax", "MiniMax"),
    ("mixtral", "Mistral AI"), ("mistral", "Mistral AI"),
    ("phi", "Microsoft"),
    ("glm", "Zhipu AI"), ("olmo", "Allen AI"), ("command", "Cohere"),
    ("kimi", "Moonshot AI"), ("moonshot", "Moonshot AI"), ("mimo", "Xiaomi"), ("nemotron", "NVIDIA"),
    ("inkling", "Thinking Machines"), ("thinkingmachines", "Thinking Machines"),
]


def developer_for(model_name):
    """Canonical developer for a model_name, or None if unmapped (guard will fail)."""
    n = (model_name or "").lower()
    for key, dev in DEVELOPER_RULES:
        if key in n:
            return dev
    return None


def verify_developers(models):
    return [f"unmapped developer for model {m!r}" for m in models if not developer_for(m)]


def verify_rank(ranked):
    """ranked: list of (rank, model, rai) in displayed order."""
    probs = []
    rais = [r for _, _, r in ranked]
    if rais != sorted(rais, reverse=True):
        probs.append(f"leaderboard is not RAI-descending: {rais}")
    if [rk for rk, _, _ in ranked] != list(range(1, len(ranked) + 1)):
        probs.append("ranks are not a contiguous 1..N")
    return probs


def verify_findings(findings_md, board_rais):
    """The Key Findings ranking table's RAI column must match the live board, in order."""
    table = [round(float(x), 1) for x in
             re.findall(r"^\|\s*\d+\s*\|[^|]+\|\s*([0-9]+\.[0-9]+)\s*\|", findings_md, re.M)]
    if not table:
        return ["no Key Findings ranking table found in findings.md"]
    want = sorted((round(r, 1) for r in board_rais), reverse=True)[:len(table)]
    if table != want:
        return [f"Key Findings table RAI {table} != live board top {want}"]
    return []


def _load_board_from_hf():
    from huggingface_hub import HfApi, hf_hub_download
    tok = os.environ.get("HF_TOKEN")
    api = HfApi(token=tok)
    repo = "cloudronin/raidex-results"
    rows = []
    for f in api.list_repo_files(repo, repo_type="dataset"):
        if not f.endswith(".json"):
            continue
        d = json.load(open(hf_hub_download(repo, f, repo_type="dataset", token=tok)))
        c, cfg = d.get("composite", {}), d.get("config", {})
        if c.get("rai_score") is not None:
            rows.append((cfg.get("model_name") or cfg.get("model_id", "?"), float(c["rai_score"])))
    rows.sort(key=lambda r: (-r[1], r[0]))   # RAI desc, then model name (deterministic ties)
    return [(i + 1, m, r) for i, (m, r) in enumerate(rows)]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ranked = _load_board_from_hf()
    models = [m for _, m, _ in ranked]
    rais = [r for _, _, r in ranked]
    findings = open(os.path.join(here, "findings.md")).read()
    problems = (verify_developers(models)
                + verify_rank(ranked)
                + verify_findings(findings, rais))
    print(f"Checked {len(models)} board models:")
    for rk, m, r in ranked:
        print(f"  #{rk:<2} {m:42} {r:5}  ->  {developer_for(m)}")
    if problems:
        print("\nINTEGRITY CHECK FAILED:")
        for p in problems:
            print("  ✗", p)
        sys.exit(1)
    print("\n✓ integrity OK: developers mapped, rank RAI-descending, Key Findings consistent")


if __name__ == "__main__":
    main()
