
import gradio as gr
from summarize_text import generate_summary


def change_input(source):

    if source == "Text":
        # Show only text input
        return (
            gr.update(value=""),          # Textbox
            gr.update(value=None),        # File
            gr.update(value="")           # URL
        )

    elif source == "Upload File":
        # Clear text and URL
        return (
            gr.update(value=""),
            gr.update(value=None),
            gr.update(value="")
        )

    elif source == "URL":
        # Clear text and file
        return (
            gr.update(value=""),
            gr.update(value=None),
            gr.update(value="")
        )
# print(gr.__version__)
with gr.Blocks(theme=gr.themes.Soft()) as demo:

    gr.Markdown("# 📚 AI Text Summarizer")
    gr.Markdown("Summarize text, uploaded files, or web pages using the Groq API.")

    input_type = gr.Radio(
        ["Text", "Upload File", "URL"],
        value="Text",
        label="Choose Input Source"
    )

    text = gr.Textbox(
        lines=12,
        label="Paste Text"
    )

    file = gr.File(
        label="Upload PDF, DOCX or TXT"
    )

    url = gr.Textbox(
        label="Website URL"
    )
    
    input_type.change(
    fn=change_input,
    inputs=input_type,
    outputs=[text, file, url]
    )
    with gr.Row():

        length = gr.Dropdown(
            ["Short","Medium","Long"],
            value="Medium",
            label="Summary Length"
        )

        style = gr.Dropdown(
            [
                "Bullet Points",
                "Paragraph",
                "Academic",
                "Business"
            ],
            value="Bullet Points",
            label="Output Style"
        )

    button = gr.Button(
        "Generate Summary"
    )

    summary = gr.Markdown()

    button.click(
        generate_summary,
        inputs=[
            input_type,
            text,
            file,
            url,
            length,
            style
        ],
        outputs=summary
    )

demo.launch(debug=True)