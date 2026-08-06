import gradio as gr

with gr.Blocks() as app:
    gr.HTML("""
    <iframe 
        src="https://1hit.no/gen/audio/mp3/" 
        width="100%" 
        height="700" 
        style="border:none;">
    </iframe>
    """)

if __name__ == "__main__":
    app.launch()