import gradio as gr


def build_face_swap_video_tab():

        gr.Markdown(
            "Upload a source face and a target video to create a face-swapped video."
        )

        sv_img = gr.Image(
            label="📷 Source Face",
            type="pil",
        )

        sv_vid = gr.File(
            label="🎥 Target Video",
        )

        sv_btn = gr.Button(
            "🎭 Swap Face",
            variant="primary",
        )

        sv_out = gr.File(
            label="🎬 Result Video",
        )

        sv_stat = gr.Textbox(
            label="Status",
            interactive=False,
        )

        return {
            "image": sv_img,
            "video": sv_vid,
            "button": sv_btn,
            "output": sv_out,
            "status": sv_stat,
        }
