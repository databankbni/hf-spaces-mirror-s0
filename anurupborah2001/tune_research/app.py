import html
import tempfile

import gradio as gr
from dotenv import load_dotenv

from research_manager import ResearchManager
from lib.env_var import NO_OF_CLARIFYING_QUESTIONS

load_dotenv(override=True)

# ---------------------------------------------------------------------------
# Tailwind CSS (Play CDN + typography plugin) and Alpine.js, injected once into
# <head>. All layout/animation/spacing is done with Tailwind utility classes
# via elem_classes; the actual look of native widgets (inputs, buttons, tabs)
# comes from the custom Gradio theme below.
# ---------------------------------------------------------------------------
HEAD = """
<script>
  window.__applyTailwindConfig = function () {
    window.tailwind.config = {
      theme: {
        extend: {
          keyframes: {
            fadeInUp: { '0%': { opacity: 0, transform: 'translateY(16px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
            fadeInDown: { '0%': { opacity: 0, transform: 'translateY(-16px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
            glowPulse: { '0%,100%': { boxShadow: '0 0 0 0 rgba(99,102,241,0.55)' }, '50%': { boxShadow: '0 0 0 9px rgba(99,102,241,0)' } },
          },
          animation: {
            fadeInUp: 'fadeInUp .5s ease both',
            fadeInDown: 'fadeInDown .6s ease both',
            glowPulse: 'glowPulse 1.6s ease-in-out infinite',
          },
        },
      },
    };
  };
</script>
<script src="https://cdn.tailwindcss.com?plugins=typography" onload="window.__applyTailwindConfig()"></script>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js"></script>
"""

# Strip Gradio's default block chrome (background/border/shadow/padding) from
# purely decorative HTML so our own Tailwind markup fully controls the look.
NOCHROME = ["!bg-transparent", "!border-0", "!shadow-none", "!p-0", "!m-0", "!min-h-0"]

CARD = [
    "!bg-white/90", "!backdrop-blur-sm", "!border", "!border-slate-200",
    "!rounded-2xl", "!shadow-xl", "!shadow-slate-200/60", "!p-5", "sm:!p-6",
    "!mb-5", "animate-fadeInUp",
]

PROSE = ["prose", "prose-sm", "sm:prose-base", "max-w-none"]

THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.indigo,
    secondary_hue=gr.themes.colors.violet,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
).set(
    body_background_fill="radial-gradient(circle at 15% 0%, #eef2ff 0%, #f8fafc 55%)",
    body_background_fill_dark="radial-gradient(circle at 15% 0%, #eef2ff 0%, #f8fafc 55%)",
    body_text_color="#1e293b",
    body_text_color_dark="#1e293b",
    block_background_fill="#ffffff",
    block_background_fill_dark="#ffffff",
    block_border_color="#e2e8f0",
    block_border_color_dark="#e2e8f0",
    block_label_text_color="#475569",
    block_label_text_color_dark="#475569",
    block_label_background_fill="#f1f5f9",
    block_label_background_fill_dark="#f1f5f9",
    block_radius="1rem",
    input_background_fill="#ffffff",
    input_background_fill_dark="#ffffff",
    input_border_color="#cbd5e1",
    input_border_color_dark="#cbd5e1",
    button_primary_background_fill="linear-gradient(90deg, #6366f1, #8b5cf6)",
    button_primary_background_fill_hover="linear-gradient(90deg, #818cf8, #a78bfa)",
    button_primary_text_color="#ffffff",
    button_secondary_background_fill="#f1f5f9",
    button_secondary_background_fill_dark="#f1f5f9",
    button_secondary_text_color="#334155",
    button_secondary_text_color_dark="#334155",
)

STEPS = ["Topic", "Clarify", "Research", "Report"]

EXAMPLE_TOPICS = [
    "The impact of AI agents on knowledge work in 2026",
    "How small businesses can adopt renewable energy affordably",
    "The current state of quantum computing for cryptography",
]


def section_header(number: int, title: str) -> str:
    return (
        "<div class='flex items-center gap-3 mb-4'>"
        f"<span class='flex items-center justify-center w-7 h-7 rounded-full "
        "bg-gradient-to-br from-indigo-500 to-violet-500 text-white text-xs font-bold shrink-0'>"
        f"{number}</span>"
        f"<h2 class='text-base sm:text-lg font-bold text-slate-800'>{title}</h2></div>"
    )


def render_stepper(active: int) -> str:
    parts = []
    for i, label in enumerate(STEPS):
        if i < active:
            circle = "bg-emerald-500 text-white border-emerald-500"
            label_cls, icon = "text-slate-600", "✓"
        elif i == active:
            circle = "bg-gradient-to-br from-indigo-500 to-violet-500 text-white border-indigo-400 animate-glowPulse"
            label_cls, icon = "text-slate-800", str(i + 1)
        else:
            circle = "bg-slate-100 text-slate-400 border-slate-300"
            label_cls, icon = "text-slate-400", str(i + 1)

        if i > 0:
            bar_cls = "bg-gradient-to-r from-indigo-500 to-violet-500" if i <= active else "bg-slate-200"
            parts.append(f"<div class='flex-1 h-0.5 {bar_cls} mx-1 sm:mx-2 mt-4 transition-colors duration-500'></div>")

        parts.append(
            "<div class='flex flex-col items-center gap-1.5 shrink-0'>"
            f"<div class='w-8 h-8 sm:w-9 sm:h-9 rounded-full border-2 flex items-center justify-center "
            f"text-xs sm:text-sm font-bold transition-all duration-300 {circle}'>{icon}</div>"
            f"<span class='text-[10px] sm:text-xs font-semibold {label_cls}'>{label}</span></div>"
        )
    return f"<div class='max-w-lg mx-auto flex items-start justify-between px-2 mb-6'>{''.join(parts)}</div>"


def render_timeline(status_log: str) -> str:
    lines = [entry.lstrip("- ").strip() for entry in status_log.splitlines() if entry.strip()]
    if not lines:
        return ""
    spinner = (
        "<svg class='animate-spin h-4 w-4 text-indigo-400 shrink-0' viewBox='0 0 24 24' fill='none'>"
        "<circle class='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' stroke-width='4'></circle>"
        "<path class='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z'></path></svg>"
    )
    rows = []
    for i, line in enumerate(lines):
        is_last = i == len(lines) - 1
        icon = spinner if is_last else "<span class='text-emerald-500 shrink-0'>✓</span>"
        color = "text-slate-800 font-medium" if is_last else "text-slate-400 line-through decoration-slate-300"
        rows.append(
            f"<div class='flex items-center gap-3 py-1.5 text-sm {color}'>{icon}<span>{html.escape(line)}</span></div>"
        )
    return f"<div class='space-y-0.5'>{''.join(rows)}</div>"


def _skeleton_bar(width_class: str) -> str:
    return f"<div class='h-3 rounded bg-slate-200 animate-pulse {width_class}'></div>"


def skeleton_html() -> str:
    bars = "".join(_skeleton_bar(w) for w in ("w-2/3", "w-full", "w-5/6", "w-full", "w-1/2"))
    return f"<div class='space-y-3 py-1'>{bars}<p class='text-xs text-slate-500 pt-2'>Drafting your report…</p></div>"


COPY_BUTTON = """
<div x-data="{copied:false}" class="flex justify-end -mb-2">
  <button type="button"
    x-on:click="navigator.clipboard.writeText(document.getElementById('dr-report-content').innerText); copied = true; setTimeout(() => copied = false, 2000)"
    class="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 border border-slate-300 transition-colors">
    <span x-show="!copied">📋 Copy report</span>
    <span x-show="copied" class="text-emerald-600">✓ Copied!</span>
  </button>
</div>
"""

SCROLL_TO_PROGRESS = "() => { document.getElementById('dr-progress-anchor')?.scrollIntoView({behavior: 'smooth', block: 'start'}); }"


async def fetch_questions(query: str):
    """ Ask the clarification agent for questions, then reveal the answer form """
    if not query or not query.strip():
        raise gr.Error("Please enter a research topic first.")

    plan = await ResearchManager().get_clarifying_questions(query)
    questions = [item.query for item in plan.queries][:NO_OF_CLARIFYING_QUESTIONS]
    while len(questions) < NO_OF_CLARIFYING_QUESTIONS:
        questions.append(f"Anything else we should know about '{query}'?")

    answer_updates = [gr.update(label=f"❓ {q}", value="", visible=True) for q in questions]
    return (
        render_stepper(1),
        questions,
        gr.update(visible=True),
        *answer_updates,
    )


async def run_research(query: str, questions: list[str], *answers: str):
    """ Combine the query with the clarifying Q&A and stream the research pipeline """
    if not questions:
        raise gr.Error("Please get clarifying questions first.")

    qna_pairs = list(zip(questions, answers))

    async for status, plan_md, report_md, summary_md, followup_md in ResearchManager().run(query, qna_pairs):
        is_done = bool(report_md)
        stage = 3 if is_done else 2
        plan_reveal = gr.update(open=True) if plan_md else gr.update()
        skeleton_update = gr.update(visible=True, value=skeleton_html()) if not is_done else gr.update(visible=False)
        download_update = gr.update(visible=False)

        if is_done:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", prefix="deep-research-", delete=False, encoding="utf-8"
            )
            tmp.write(report_md)
            tmp.close()
            download_update = gr.update(value=tmp.name, visible=True)

        yield (
            render_stepper(stage),
            render_timeline(status),
            plan_reveal,
            plan_md or "_Waiting for the planner agent..._",
            skeleton_update,
            report_md or "",
            summary_md,
            followup_md,
            download_update,
        )


with gr.Blocks(theme=THEME, head=HEAD, title="Deep Research") as ui:
    gr.HTML(
        "<div class='max-w-3xl mx-auto text-center pt-8 sm:pt-10 pb-2 animate-fadeInDown'>"
        "<div class='inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 "
        "ring-1 ring-indigo-200 text-indigo-700 text-xs font-medium mb-4'>"
        "<span class='relative flex h-2 w-2'>"
        "<span class='animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75'></span>"
        "<span class='relative inline-flex rounded-full h-2 w-2 bg-indigo-500'></span></span>"
        "AI Research Assistant</div>"
        "<h1 class='text-3xl sm:text-5xl font-extrabold tracking-tight bg-clip-text text-transparent "
        "bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-600'>Deep Research</h1>"
        "<p class='mt-3 text-slate-600 text-sm sm:text-base max-w-xl mx-auto'>Answer a few quick questions "
        "and get a fully researched report — delivered straight to your inbox or phone.</p></div>",
        elem_classes=NOCHROME,
    )

    stepper = gr.HTML(render_stepper(0), elem_classes=NOCHROME)

    with gr.Group(elem_classes=CARD):
        gr.HTML(section_header(1, "What would you like researched?"), elem_classes=NOCHROME)
        query_box = gr.Textbox(
            placeholder="e.g. The impact of AI agents on knowledge work in 2026",
            label="Research topic",
            lines=2,
            elem_classes=["w-full"],
        )
        gr.Examples(examples=EXAMPLE_TOPICS, inputs=query_box, label="Need inspiration? Try one of these")
        get_questions_btn = gr.Button("✨ Get Clarifying Questions", variant="primary", elem_classes=["w-full", "sm:w-auto", "mt-1"])

    questions_state = gr.State([])

    with gr.Group(visible=False, elem_classes=CARD) as qna_group:
        gr.HTML(section_header(2, "A few quick questions"), elem_classes=NOCHROME)
        answer_1 = gr.Textbox(label="Question 1", lines=1, elem_classes=["w-full"])
        answer_2 = gr.Textbox(label="Question 2", lines=1, elem_classes=["w-full"])
        answer_3 = gr.Textbox(label="Question 3", lines=1, elem_classes=["w-full"])
        start_btn = gr.Button("🚀 Start Deep Research", variant="primary", elem_classes=["w-full", "sm:w-auto", "mt-1"])

    gr.HTML("<div id='dr-progress-anchor'></div>", elem_classes=NOCHROME)

    with gr.Group(elem_classes=CARD):
        gr.HTML(section_header(3, "Progress"), elem_classes=NOCHROME)
        status_html = gr.HTML(elem_classes=NOCHROME)
        with gr.Accordion("🔍 How this report is being researched", open=False) as plan_accordion:
            plan_md = gr.Markdown("_The search plan will appear here once the planner agent runs._", elem_classes=PROSE)

    with gr.Group(elem_classes=CARD):
        gr.HTML(section_header(4, "Report"), elem_classes=NOCHROME)
        skeleton = gr.HTML(visible=False, elem_classes=NOCHROME)
        gr.HTML(COPY_BUTTON, elem_classes=NOCHROME)
        with gr.Tabs():
            with gr.TabItem("📄 Full report"):
                report_md = gr.Markdown(elem_id="dr-report-content", elem_classes=PROSE)
            with gr.TabItem("📝 Summary"):
                summary_md = gr.Markdown(elem_classes=PROSE)
            with gr.TabItem("🔮 Follow-up ideas"):
                followup_md = gr.Markdown(elem_classes=PROSE)
        download_btn = gr.DownloadButton("⬇️ Download report (.md)", visible=False, elem_classes=["w-full", "sm:w-auto", "mt-1"])

    gr.HTML(
        "<p class='text-center text-slate-500 text-xs py-6'>Powered by OpenAI Agents · "
        "Reports are sent by email or Pushover when ready</p>",
        elem_classes=NOCHROME,
    )

    get_questions_btn.click(
        fn=fetch_questions,
        inputs=[query_box],
        outputs=[stepper, questions_state, qna_group, answer_1, answer_2, answer_3],
    ).then(fn=None, js=SCROLL_TO_PROGRESS)

    start_btn.click(
        fn=run_research,
        inputs=[query_box, questions_state, answer_1, answer_2, answer_3],
        outputs=[stepper, status_html, plan_accordion, plan_md, skeleton, report_md, summary_md, followup_md, download_btn],
    ).then(fn=None, js=SCROLL_TO_PROGRESS)

ui.queue()

if __name__ == "__main__":
    ui.launch(inbrowser=True)
