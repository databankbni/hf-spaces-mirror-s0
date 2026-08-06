import gradio as gr
from config import DEFAULT_NEGATIVE
from engines.faceid_engine import generate_ip_adapter_scene

def build_identity_lock_tab():
            ip_face = gr.Image(label="source Face", type="filepath")
            ip_prompt = gr.Textbox(label="scene Prompt", lines=4)
            ip_neg = gr.Textbox(label="Negative prompt", value=DEFAULT_NEGATIVE)
            with gr.Row():
                ip_w = gr.Number(label="Width", value=768)
                ip_h = gr.Number(label="Height", value=1024)
                ip_s = gr.Number(label="Steps", value=30)
                ip_zd = gr.Number(label="Seed", value=0)
                ip_str = gr.Slider(0.5, 1.2, value=0.7, step=0.05, label="Identity Strength")
            ip_btn = gr.Button("🧬 Generate scene")
            ip_out = gr.Image(label="generate")
            ip_stat = gr.Markdown()
            ip_btn.click(generate_ip_adapter_scene, [ip_face, ip_prompt, ip_neg, ip_w, ip_h, ip_s, ip_zd, ip_str], [ip_out, ip_stat])
