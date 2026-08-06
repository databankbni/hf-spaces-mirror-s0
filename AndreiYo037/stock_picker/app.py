"""Gradio UI for the Stock Picker CrewAI project."""

import asyncio
import json
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
OUTPUT_DIR = PROJECT_ROOT / "output"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

OUTPUT_DIR.mkdir(exist_ok=True)

TRENDING_PATH = OUTPUT_DIR / "trending_companies.json"
RESEARCH_PATH = OUTPUT_DIR / "research_report.json"
DECISION_PATH = OUTPUT_DIR / "decision.md"

SECTOR_EXAMPLES = [
    "Technology",
    "Healthcare",
    "Energy",
    "Financial Services",
    "Consumer Goods",
]


def load_env_files() -> None:
    load_dotenv(override=True)
    for parent in Path(__file__).resolve().parents:
        env_path = parent / ".env"
        if env_path.is_file():
            load_dotenv(env_path, override=True)
            break


load_env_files()


def _missing_keys() -> list[str]:
    missing = []
    for name in ("OPENAI_API_KEY", "SERPER_API_KEY"):
        if not os.environ.get(name, "").strip():
            missing.append(name)
    return missing


def _format_trending() -> str:
    if not TRENDING_PATH.is_file():
        return "_No trending companies file yet._"
    data = json.loads(TRENDING_PATH.read_text(encoding="utf-8"))
    companies = data.get("companies", data if isinstance(data, list) else [])
    if not companies:
        return "_No trending companies found._"
    lines = ["### Trending companies\n"]
    for c in companies:
        lines.append(
            f"- **{c.get('name', 'Unknown')}** (`{c.get('ticker', '—')}`) — "
            f"{c.get('reason', '')}"
        )
    return "\n".join(lines)


def _format_research() -> str:
    if not RESEARCH_PATH.is_file():
        return "_No research report yet._"
    data = json.loads(RESEARCH_PATH.read_text(encoding="utf-8"))
    items = data.get("research_list", data if isinstance(data, list) else [])
    if not items:
        return "_No research entries found._"
    lines = ["### Research summary\n"]
    for item in items:
        lines.append(f"#### {item.get('name', 'Unknown')}\n")
        lines.append(f"**Market position:** {item.get('market_position', '—')}\n")
        lines.append(f"**Future outlook:** {item.get('future_outlook', '—')}\n")
        lines.append(
            f"**Investment potential:** {item.get('investment_potential', '—')}\n"
        )
    return "\n".join(lines)


def _format_decision(result) -> str:
    if DECISION_PATH.is_file():
        return DECISION_PATH.read_text(encoding="utf-8")
    return str(getattr(result, "raw", result))


def _build_report(result) -> str:
    sections = [
        f"_Generated {datetime.now().date()}. Not financial advice._\n",
        _format_decision(result),
        "---\n",
        _format_trending(),
        "---\n",
        _format_research(),
    ]
    return "\n\n".join(sections)


def _run_crew(sector: str):
    warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")
    from stock_picker.crew import StockPicker

    inputs = {
        "sector": sector,
        "current_date": str(datetime.now().date()),
    }
    return StockPicker().crew().kickoff(inputs=inputs)


async def pick_stock(sector: str):
    sector = (sector or "").strip()
    if not sector:
        yield "Enter a sector to analyze."
        return

    missing = _missing_keys()
    if missing:
        yield (
            "### Configuration error\n\n"
            "Missing required environment variables:\n\n"
            + "\n".join(f"- `{k}`" for k in missing)
            + "\n\nAdd them under **Space Settings → Secrets**, then restart the Space."
        )
        return

    yield (
        f"### Analyzing **{sector}**\n\n"
        f"**Date context:** {datetime.now().date()}\n\n"
        "The crew is running:\n"
        "1. **Trending company finder** — scan news for hot companies\n"
        "2. **Financial researcher** — deep-dive each candidate\n"
        "3. **Stock picker** — choose the best investment and notify\n\n"
        "_This usually takes several minutes…_"
    )

    try:
        result = await asyncio.to_thread(_run_crew, sector)
        yield _build_report(result)
    except ConnectionError as exc:
        yield (
            "### Error\n\n"
            f"Could not reach the OpenAI API.\n\n```\n{exc}\n```\n\n"
            "Check that `OPENAI_API_KEY` is set correctly in your `.env` file."
        )
    except Exception as exc:
        yield f"### Error\n\n```\n{exc}\n```"


with gr.Blocks(title="Stock Picker") as demo:
    gr.Markdown(
        "# Stock Picker\n\n"
        "CrewAI crew: find trending companies in a sector, research them, "
        "then pick the best investment. Optional Pushover notification if configured."
    )

    with gr.Row():
        sector_input = gr.Textbox(
            label="Sector",
            placeholder="e.g. Technology",
            scale=4,
        )
        run_button = gr.Button("Pick stock", variant="primary", scale=1)

    gr.Examples(examples=SECTOR_EXAMPLES, inputs=sector_input)

    report = gr.Markdown(label="Results")

    run_button.click(fn=pick_stock, inputs=sector_input, outputs=report)
    sector_input.submit(fn=pick_stock, inputs=sector_input, outputs=report)


if __name__ == "__main__":
    default_port = "7860" if os.environ.get("SPACE_ID") else "7862"
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", default_port)),
        inbrowser=not os.environ.get("SPACE_ID"),
    )
