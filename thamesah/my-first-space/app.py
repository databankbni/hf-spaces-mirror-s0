
import gradio as gr

def respond(message, history):
    response = f"you said {message}\
         \n\n and I say I love everything I do!"
    return response

gr.ChatInterface(fn=respond).launch()