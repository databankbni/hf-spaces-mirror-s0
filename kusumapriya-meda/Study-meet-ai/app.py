from google import genai
import gradio as gr
import os
# Gemini API key
client = genai.Client(api_key=os.getenv("Google_apikey"))

def generate_blogs(topic, persona, seo_keyword, format_type, words):
    prompt = f"""
    Write a {int(words)}-word blog post in {format_type} format.
    Topic: {topic}
    Persona/Tone: {persona}
    SEO Keyword to include naturally: {seo_keyword}

    Include:
    - Catchy Title
    - A hook (a surprising statistic or a thought-provoking question)
    - 3 main bullet points or sub-headings exploring the topic
    - A 'Pro Tip' or 'Expert Insight' section
    - A brief 'Common Misconceptions' section to address myths
    - A clear call-to-action (CTA)
    - Conclusion
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text

demo = gr.Interface(
    fn=generate_blogs,
    inputs=[
        gr.Textbox(label="Topic"),
        gr.Dropdown(["Tech Expert", "Friendly Student", "Storyteller"], label="Persona"),
        gr.Textbox(label="SEO Keyword"),
        gr.Radio(["Listicle", "How-to Guide", "Opinion Piece"], label="Format"),
        gr.Slider(minimum=200, maximum=1000, label="Word Count")
    ],
    outputs="markdown",  # renders bold/headers nicely
    title="AI Blog Generator"
)

demo.launch()