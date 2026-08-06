import gradio as gr
from config import*
from engines.lora_engine import generate_lora


def build_lora_tab():
    lora_prompt = gr.Textbox(
        label="💬 LoRA Prompt",
        lines=4,
        value="gnrwoman01, candid DSLR portrait photo, high quality",
        placeholder="Describe the image you want to generate...",
    )

    lora_url = gr.Textbox(
        label="🔗 LoRA Weights URL",
    )

    with gr.Accordion("⚙️ Advanced Settings", open=False):

        lora_negative = gr.Textbox(
            label="Negative Prompt",
            value=DEFAULT_NEGATIVE,
        )

        lora_model = gr.Textbox(
            label="LoRA Model",
            value=DEFAULT_LORA_MODEL,
            visible=False,
        )

        lora_scale = gr.Slider(
            0.01,
            1.5,
            value=0.8,
            step=0.05,
            label="LoRA Scale",
        )

        with gr.Row():

            lora_width = gr.Number(
                label="Width",
                value=1024,
                visible=False,
            )

            lora_height = gr.Number(
                label="Height",
                value=1024,
                visible=False,
            )

        with gr.Row():

            lora_steps = gr.Number(
                label="Steps",
                value=33,
                visible=False,
            )

            lora_seed = gr.Number(
                label="Seed (0 = Random)",
                value=0,
                precision=0,
                visible=False,
            )

    lora_btn = gr.Button(
        "✨ Generate LoRA",
        variant="primary",
    )

    lora_output = gr.Image(
        label="🖼️ Generated Image",
    )

    lora_status = gr.Textbox(
        label="Status",
        interactive=False,
    )

    lora_btn.click(
        generate_lora,
        [
            lora_prompt,
            lora_negative,
            lora_model,
            lora_url,
            lora_scale,
            lora_width,
            lora_height,
            lora_steps,
            lora_seed,
        ],
        [
            lora_output,
            lora_status,
        ],
    )
