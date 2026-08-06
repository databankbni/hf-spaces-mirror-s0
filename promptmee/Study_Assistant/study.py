import subprocess
import sys

# Force-install/upgrade the correct library at runtime before importing
try:
    from google import genai
    from google.genai import types
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "google-genai"])
    from google import genai
    from google.genai import types

import os
import gradio as gr
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

personalities = {
     "Friendly":
          "You are a friendly, enthusiastic, and highly encouraging Study Assistant. Your goal is to break down complex concepts into simple, beginner-friendly explanations. Use analogies and real-world examples that beginners can relate to. Always ask a follow-up question to check understanding",
      "Academic":
            "You are a strictly academic, highly detailed, and professional university Professor. Use precise, formal terminology, cite key concepts and structure your response. Your goal is to break down complex concepts into simple, beginner-friendly explanations. Use analogies and real-world examples that beginners can relate to. Always ask a follow-up question to check understanding"
}

def study_assistant(question, persona):
  system_prompt = personalities[persona]
  response = client.models.generate_content(
        model = "gemini-2.5-flash",
        config = types.GenerateContentConfig(
            system_instruction = system_prompt,
            temperature = 0.4,
            max_output_tokens = 10000
        ),
        contents = question
    )
  return response.text
 
demo = gr.Interface(
    fn = study_assistant,
    inputs = [gr.Textbox(label="Question", lines=4, placeholder="Ask a question..."),
                gr.Dropdown(choices=list(personalities.keys()), value="Friendly", label="Personality")],
    outputs = gr.Textbox(label="Explanation", lines=10),
    title = "Study Assistant",
    description = "Ask a question to get simple explanation from AI along with analogies and real world examples."
)

demo.launch(debug=True)