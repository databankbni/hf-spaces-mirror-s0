import gradio as gr


def build_face_video_tab():

        gr.Markdown(
            "Upload a face image and describe the motion you'd like to generate."
        )

        fv_img = gr.Image(
            label="📷 Source Face",
            type="pil",
        )

        fv_prom = gr.Textbox(
            label="💬 Motion Prompt",
            placeholder="Example: Natural smile and blink while looking at the camera...",
            value="Natural smile and blink",
        )

        fv_btn = gr.Button(
            "🎬 Generate Video",
            variant="primary",
        )

        fv_out = gr.Video(
            label="🎥 Result Video",
        )

        fv_stat = gr.Textbox(
            label="Status",
            interactive=False,
        )

        return {
            "image": fv_img,
            "prompt": fv_prom,
            "button": fv_btn,
            "output": fv_out,
            "status": fv_stat,
        }

           
