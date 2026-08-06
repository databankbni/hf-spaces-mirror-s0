import gradio as gr

demo = gr.Interface(fn=lambda x: f"Hello {x}!", inputs="text", outputs="text")
demo.launch()
