import gradio as gr

from engines.img2img_engine import generate_img2img_local

def build_img2img_tab():

        img2img_model = gr.Textbox(
            label="HF Model ID",
            value="runwayml/stable-diffusion-v1-5",
            visible=False,
        )

        img2img_prompt = gr.Textbox(
            label="💬 Prompt",
            lines=4,
            placeholder="Describe how you want to transform the image...",
        )

        with gr.Row():
            img2img_input = gr.Image(
                label="🖼️ Original Image",
                type="pil",
            )

            img2img_input_2 = gr.Image(
                label="🖼️ Reference Image (Optional)",
                type="pil",
            )

        with gr.Accordion("⚙️ Advanced Settings", open=False):

            img2img_strength = gr.Slider(
                0.0, 1.0,
                value=0.35,
                step=0.05,
                label="Edit Strength",
            )

            img2img_guidance = gr.Slider(
                1.0, 20.0,
                value=5.5,
                step=0.5,
                label="CFG",
            )

            img2img_face_blend = gr.Slider(
                0.0, 1.0,
                value=0.95,
                step=0.05,
                label="Face Blend",
            )

            with gr.Row():

                img2img_steps = gr.Number(
                    label="Steps",
                    value=30,
                )

                img2img_seed = gr.Number(
                    label="Seed",
                    value=0,
                    precision=0,
                )

                img2img_preserve = gr.Checkbox(
                    label="Preserve Original Face",
                    value=True,
                )

        img2img_btn = gr.Button(
            "🎨 Generate Image",
            variant="primary",
        )

        img2img_output = gr.Image(
            label="🖼️ Result",
        )

        img2img_status = gr.Textbox(
            label="Status",
            interactive=False,
        )

        img2img_btn.click(
            generate_img2img_local,
            [
                img2img_prompt,
                img2img_input,
                img2img_input_2,
                img2img_model,
                img2img_strength,
                img2img_guidance,
                img2img_steps,
                img2img_seed,
                img2img_preserve,
                img2img_face_blend,
            ],
            [
                img2img_output,
                img2img_status,
            ],
        )

