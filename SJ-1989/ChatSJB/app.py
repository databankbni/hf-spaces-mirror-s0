import logging
from pathlib import Path
import gradio as gr
from chatbot.chatbot import chatbot

gr.set_static_paths(
    paths=["."]
)

# -------------------------
# Logging
# -------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S'
)

for logger_name in [
    'httpx',
    'httpcore',
    'urllib3',
    'google_genai.models',
    'gradio',
    'huggingface_hub',
]:
    logging.getLogger(logger_name).setLevel(logging.ERROR)

# -------------------------
# CSS styles
# -------------------------

css = Path("styles.css").read_text()

# -------------------------
# Gradio UI
# -------------------------

theme = (
    gr.themes.Soft(
        primary_hue="blue",
        neutral_hue="slate",
    )
    .set(
        body_background_fill="#0f172a",
        body_background_fill_dark="#0f172a",

        block_background_fill="#1e293b",
        block_background_fill_dark="#1e293b",

        input_background_fill="#1e293b",
        input_background_fill_dark="#1e293b",

        body_text_color="#f8fafc",
        body_text_color_dark="#f8fafc",

        block_border_color="#334155",
        block_border_color_dark="#334155",

        button_secondary_background_fill="#f8fafc",
        button_secondary_background_fill_hover="#e2e8f0",
        button_secondary_border_color="#f8fafc",
        button_secondary_text_color="#0f172a",
    )
)

with gr.Blocks(
    title="Saint James Backpackers Assistant",
) as demo:

    gr.HTML(
    '''
    <img 
        class="logo"
        width="100"
        height="100"
        src="/gradio_api/file=Logo.png"
    >
    ''',
    elem_id="logo-container",
)

    gr.Markdown(
        """
#### Hi, my name's Jack 👋
#### I'm your virtual assistant!
""",
        elem_id="intro",
    )

    gr.Markdown(
        """
I can help you with:
- 🛎️ Our services
- 📋 House rules
- 📍 Travel directions
""",
        elem_id="explanation",
    )

    question = gr.Textbox(
        label=None,
        show_label=False,
        placeholder="Your question...",
        lines=1,
    )

    with gr.Row():
        ask_button = gr.Button(
            "Ask",
            variant="primary",
        )

        clear_button = gr.Button(
            "Clear",
            elem_id="clear-button",
        )

    answer = gr.Markdown(
        label="Answer",
        elem_id="answer",
    )

    ask_button.click(
        fn=chatbot,
        inputs=question,
        outputs=answer,
    )

    question.submit(
        fn=chatbot,
        inputs=question,
        outputs=answer,
    )

    clear_button.click(
        lambda: ("", ""),
        outputs=[question, answer],
    )

# -------------------------
# Entry point
# -------------------------

if __name__ == "__main__":
    demo.launch(
        theme=theme,
        css=css,
    )