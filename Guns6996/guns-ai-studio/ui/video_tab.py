import gradio as gr
from engines.video_engine import generate_video_with_provider, toggle_model_id

def build_video_tab():
    video_provider = gr.Dropdown(
        choices=[
            "RunPod",
            "Hugging Face LTX",
            "Hugging Face CogVideoX",
        ],
        value="Hugging Face LTX",
        label="Video Engine",
    )

    v_img = gr.Image(
        label="🖼️ Source Image",
        type="pil",
    )

    v_prom = gr.Textbox(
        label="💬 Motion Prompt",
        value="Natural camera movement",
        placeholder="Describe how you want the image to move...",
    )

    v_btn = gr.Button(
        "🎬 Generate Video",
        variant="primary",
    )

    v_out = gr.Video(
        label="🎥 Generated Video",
    )

    v_stat = gr.Textbox(
        label="Status",
        interactive=False,
    )

    v_btn.click(
        fn=generate_video_with_provider,
        inputs=[
            video_provider,
            v_img,
            v_prom,
            custom_server_url_display,
        ],
        outputs=[
            v_out,
            v_stat,
        ],
    )