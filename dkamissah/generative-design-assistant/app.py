"""
Gradio UI for the Generative Design Assistant.
HF Spaces entry point — with step-by-step progress and PDF export.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import gradio as gr
from src.agent.design_agent import DesignAgent
from src.tools.pdf_exporter import export_pdf
from src.tools.docx_exporter import export_docx

agent      = DesignAgent()
last_result = {}   # store last run for PDF export

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
* { font-family: 'Inter', sans-serif !important; }
.gradio-container { max-width: 1100px !important; margin: 0 auto !important; }
#run-btn    { background: #2E75B6 !important; color: white !important; font-weight: 600 !important; border-radius: 8px !important; font-size: 1rem !important; }
#reset-btn  { background: #f0f4f8 !important; color: #2E75B6 !important; font-weight: 600 !important; border-radius: 8px !important; border: 2px solid #2E75B6 !important; }
#export-btn { background: #1F4E79 !important; color: white !important; font-weight: 600 !important; border-radius: 8px !important; }
"""

EXAMPLES = [
    "Design a lightweight suspension bracket for a BMW BEV platform. Requirements: maximum weight 1.5kg, minimum yield strength 350MPa, must withstand 5kN load in three directions, operating temperature -40 to +120C, must be manufacturable at 100,000 units/year, target cost 8 EUR per unit. Priority: weight reduction.",
    "Design a battery pack housing for a 100kWh BEV battery system. Requirements: protect cells from impact and thermal runaway, IP67 water/dust protection, maximum weight 45kg for the housing, integration with vehicle floor structure, must pass FMVSS 305 and ECE-R100, volume constraint 2400 x 1500 x 150mm. Priority: performance and safety.",
    "Design a door inner panel for a premium sedan. Requirements: integrate window regulator, speaker mounting, and door latch mechanism, minimum dent resistance, NVH damping, mass target 4.2kg, production volume 200,000 units/year, fit within existing tooling budget. Priority: cost.",
]


def run_agent(requirements_text: str):
    global last_result

    if not requirements_text.strip():
        yield ("Please enter engineering requirements.", "", "",
               gr.update(visible=True), gr.update(visible=False),
               gr.update(visible=False), gr.update(visible=False),
               gr.update(visible=False), gr.update(visible=False))
        return

    # Step 1
    yield ("**Step 1/4** — Parsing requirements...", "", "",
           gr.update(visible=False), gr.update(visible=False),
           gr.update(visible=False), gr.update(visible=False),
           gr.update(visible=False), gr.update(visible=False))

    try:
        requirements = agent.parser.parse(requirements_text)

        # Step 2
        yield (f"**Step 2/4** — Retrieving engineering knowledge for **{requirements.get('component_name', 'component')}**...",
               "", "",
               gr.update(visible=False), gr.update(visible=False),
               gr.update(visible=False), gr.update(visible=False),
               gr.update(visible=False), gr.update(visible=False))

        knowledge = agent.retriever.retrieve_for_requirements(requirements)
        context   = agent.retriever.format_context(knowledge)

        # Step 3
        yield ("**Step 3/4** — Generating 3 design alternatives...", "", "",
               gr.update(visible=False), gr.update(visible=False),
               gr.update(visible=False), gr.update(visible=False),
               gr.update(visible=False), gr.update(visible=False))

        alternatives = agent.generator.generate(requirements, context)

        # Step 4
        yield ("**Step 4/4** — Evaluating alternatives and writing feasibility report...",
               "", "",
               gr.update(visible=False), gr.update(visible=False),
               gr.update(visible=False), gr.update(visible=False),
               gr.update(visible=False), gr.update(visible=False))

        evaluation = agent.evaluator.evaluate(requirements, alternatives)
        report     = agent.evaluator.generate_report(requirements, knowledge, alternatives, evaluation)

        last_result = {
            "requirements": requirements,
            "knowledge":    knowledge,
            "alternatives": alternatives,
            "evaluation":   evaluation,
            "report":       report,
            "pipeline_ms":  0,
        }

        # Format outputs
        req = requirements
        ev  = evaluation
        rep = report
        alts = alternatives

        req_md = f"""## Parsed Requirements

**Component:** {req.get('component_name', '')}  
**Priority:** {req.get('priority', '').upper()}  
**Design Space:** {req.get('design_space', '')}

**Functional Requirements:**
{chr(10).join(f"- {r}" for r in req.get('functional_requirements', []))}

**Performance Targets:**
{chr(10).join(f"- {k}: {v}" for k, v in req.get('performance_targets', {}).items())}

**Constraints:**
{chr(10).join(f"- {c}" for c in req.get('constraints', []))}
"""

        rec_id  = ev.get("recommended", "B")
        alts_md = "## Design Alternatives\n\n"
        for alt in alts:
            score  = ev.get("scores", {}).get(alt["id"], "N/A")
            risk   = ev.get("risk_assessment", {}).get(alt["id"], "MEDIUM")
            marker = " RECOMMENDED" if alt["id"] == rec_id else ""
            alts_md += f"""### Alternative {alt['id']}: {alt['name']}{marker}

| | |
|---|---|
| **Material** | {alt.get('material', '')} |
| **Process** | {alt.get('manufacturing_process', '')} |
| **Weight** | {alt.get('estimated_weight_kg', '')} kg |
| **Cost Index** | {alt.get('estimated_cost_index', '')}/5 |
| **Performance** | {alt.get('performance_score', '')}/5 |
| **Sustainability** | {alt.get('sustainability_score', '')}/5 |
| **Overall Score** | **{score}/100** |
| **Risk** | {risk} |

{alt.get('concept', '')}

**Advantages:** {' · '.join(alt.get('advantages', [])[:2])}  
**Disadvantages:** {' · '.join(alt.get('disadvantages', [])[:1])}

"""

        ranking    = ev.get("ranking", [])
        full_report = f"""## Feasibility Report — {rep.get('report_id', '')}

### Recommendation: Alternative {rec_id}

{ev.get('recommendation_rationale', '')}

**Ranking:** {' > '.join(ranking)}

### Next Steps
{chr(10).join(f"{i+1}. {s}" for i, s in enumerate(rep.get('next_steps', [])))}

### Knowledge Sources
{chr(10).join(f"- {s}" for s in rep.get('knowledge_sources', []))}
"""

        yield (req_md, alts_md, full_report,
               gr.update(visible=False), gr.update(visible=True),
               gr.update(visible=True), gr.update(visible=True),
               gr.update(visible=False), gr.update(visible=False))

    except Exception as err:
        yield (f"Error: {str(err)}", "", "",
               gr.update(visible=True), gr.update(visible=False),
               gr.update(visible=False), gr.update(visible=False),
               gr.update(visible=False), gr.update(visible=False))


def export_to_pdf():
    global last_result
    if not last_result:
        return gr.update(visible=False)
    try:
        path = export_pdf(last_result)
        return gr.update(visible=True, value=path)
    except Exception:
        return gr.update(visible=False)


def export_to_docx():
    global last_result
    if not last_result:
        return gr.update(visible=False)
    try:
        path = export_docx(last_result)
        return gr.update(visible=True, value=path)
    except Exception:
        return gr.update(visible=False)


def reset():
    global last_result
    last_result = {}
    return ("", "", "", "",
            gr.update(visible=True), gr.update(visible=False),
            gr.update(visible=False), gr.update(visible=False),
            gr.update(visible=False), gr.update(visible=False))


with gr.Blocks(title="Generative Design Assistant") as demo:

    gr.Markdown("""
    # Generative Design Assistant
    ### AI-Powered Engineering Requirements Analysis & Design Generation

    Describe your engineering component requirements in plain text. The agent will:
    1. **Parse** structured requirements from your description
    2. **Retrieve** relevant engineering knowledge from research papers
    3. **Generate** 3 design alternatives with trade-off analysis
    4. **Evaluate** and recommend the best alternative with a feasibility report

    You can export the full feasibility report as PDF or Word document for sharing and documentation.
    """)

    with gr.Row():
        with gr.Column(scale=1):
            requirements_input = gr.Textbox(
                label       = "Engineering Requirements",
                placeholder = "Describe your component: function, loads, weight targets, constraints, production volume...",
                lines       = 8,
            )

            run_btn    = gr.Button("Generate Designs", variant="primary", elem_id="run-btn",   visible=True)
            reset_btn  = gr.Button("New Design Brief",                    elem_id="reset-btn",  visible=False)
            export_btn  = gr.Button("📄 Export PDF Report",  elem_id="export-btn", visible=False)
            docx_btn    = gr.Button("📝 Export Word Report", elem_id="export-btn", visible=False)
            pdf_file    = gr.File(label="Download PDF",  visible=False)
            docx_file   = gr.File(label="Download Word", visible=False)

            gr.Examples(examples=EXAMPLES, inputs=requirements_input, label="Example Requirements")

        with gr.Column(scale=2):
            with gr.Tabs():
                with gr.Tab("📋 Requirements"):
                    req_out = gr.Markdown()
                with gr.Tab("🔧 Design Alternatives"):
                    alts_out = gr.Markdown()
                with gr.Tab("📊 Feasibility Report"):
                    report_out = gr.Markdown()

    run_btn.click(
        fn      = run_agent,
        inputs  = [requirements_input],
        outputs = [req_out, alts_out, report_out, run_btn, reset_btn, export_btn, docx_btn, pdf_file, docx_file],
        show_progress = "hidden",
    )

    export_btn.click(
        fn      = export_to_pdf,
        inputs  = [],
        outputs = [pdf_file],
    )

    docx_btn.click(
        fn      = export_to_docx,
        inputs  = [],
        outputs = [docx_file],
    )

    reset_btn.click(
        fn      = reset,
        inputs  = [],
        outputs = [requirements_input, req_out, alts_out, report_out,
                   run_btn, reset_btn, export_btn, docx_btn, pdf_file, docx_file],
    )

    gr.Markdown("""
    ---
    **Stack:** LangChain-style agent · arXiv + Semantic Scholar · ChromaDB · sentence-transformers · Mistral-7B / Ollama · FastAPI · Gradio  
    **GitHub:** [generative-design-assistant](https://github.com/danielamissah/generative-design-assistant)
    """)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, css=CSS)