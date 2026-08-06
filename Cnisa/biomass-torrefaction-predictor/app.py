import gradio as gr
import os


hf_token = os.environ.get("HF_TOKEN")
target_space = os.environ.get("SECRET_SPACE_NAME")

demo = gr.load(name=target_space, src="spaces", token=hf_token)
demo.launch()