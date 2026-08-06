import os
import gradio as gr
from huggingface_hub import InferenceClient
from datasets import Dataset
from sentence_transformers import SentenceTransformer
from transformers import pipeline

# Initialize Inference Client
client = InferenceClient("Qwen/Qwen2.5-7B-Instruct")

def respond(message, history):
    messages = [
        {
            "role": "system",
            "content": (
                "You are Athena, an AI college application assistant. "
                "You are friendly, supportive, and guide students through the college process. "
                "Ask students guiding questions about their grade, GPA, subjects, "
                "career interests, college environment, and extracurriculars. "
                "The website has two tools available: "
                "1. Acceptance Calculator: helps students understand college chances "
                "using GPA, SAT, and ACT information. Recommend this when helpful. "
                "2. Career Navigation Tool: helps students explore careers and majors. "
                "Recommend this when students need help choosing a path."
            )
        }
    ]
    if history:
        messages.extend(history)
    messages.append({
        "role": "user",
        "content": message
    })
    response = client.chat_completion(
        messages,
        max_tokens=250
    )
    return response.choices[0].message.content.strip()

def chat(message, history):
    response = respond(message, history)
    history.append({
        "role": "user",
        "content": message
    })
    history.append({
        "role": "assistant",
        "content": response
    })
    return "", history

with gr.Blocks() as demo:
    # Load Google Fonts cleanly via HTML header
    gr.HTML("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Montserrat:wght@600;700&display=swap" rel="stylesheet">
    """)

    # Banner
    gr.Image(
        value="athena_banner.png",
        show_label=False,
        container=False,
        elem_id="athena_banner"
    )
    # Subtitle
    gr.HTML("""
    <div class="athena-header">
        <h2>Your AI College Application Assistant</h2>
        <p>
        Plan your academics, explore careers, and strengthen your college journey.
        </p>    </div>
    """)
    chatbot = gr.Chatbot(
        value=[
            {
                "role": "assistant",
                "content": "Hi! I'm Athena, your AI college application assistant. I can help you strengthen your application, explore careers, and prepare for college. First, what grade are you in?"
            }
        ]
    )
    message = gr.Textbox(
        placeholder="Message Athena..."
    )
    message.submit(
        chat,
        inputs=[message, chatbot],
        outputs=[message, chatbot]
    )
    gr.HTML("""
    <h3 class="section-title">
    📖🍃 Helpful Tools
    </h3>
    """)
    with gr.Row(elem_classes="button-row"):
        gr.HTML("""
        <a href="https://www.gradgpt.com/college-admissions-calculator" target="_blank">
        <button>
        Acceptance Calculator
        </button>
        </a>
        """)
        gr.HTML("""
        <a href="https://futurescape.britebound.org/" target="_blank">
        <button>
        Career Navigation
        </button>
        </a>
        """)
    gr.HTML("""
    <h3 class="section-title">
    🎧🌿 Study Playlist
    </h3>
    """)
    gr.HTML("""
    <iframe
    style="border-radius:12px"
    src="https://open.spotify.com/embed/playlist/4XkuOq4oGg6xrFcaeQzu6B"
    width="100%"
    height="352"
    frameBorder="0"
    allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
    loading="lazy">
    </iframe>
    """)

# Launching Demo with Advanced Styling Overrides
demo.launch(
    css="""
body {
    background-color:#e7decd !important;
}
.gradio-container {
    background-color:#e7decd !important;
    font-family:'Inter', sans-serif;
}

/* 🖼️ BANNER CLEANUP: Completely strips all green/accent backgrounds */
#athena_banner,
#athena_banner *,
.gradio-container div:has(> #athena_banner),
.block.gradio-image,
.image-container {
    background: transparent !important;
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    margin: 0 auto 15px auto !important;
}
#athena_banner img {
    display: block !important;
    width: 85% !important;        
    max-width: 800px !important;   
    height: auto !important;       
    max-height: 180px !important;  
    object-fit: cover !important;
    border-radius: 15px !important;
    margin: 0 auto !important;
}

/* Subtitle */
.athena-header {
    text-align:center !important;
}
.athena-header h2 {
    color:#804e49 !important;
    font-size:32px !important;
}
.athena-header p {
    color:#804e49 !important;
    font-size:21px !important;
}
/* Section titles */
.section-title {
    color:#804e49 !important;
    font-size:28px !important;
    text-align:center !important;
}

/* Chatbot Outer Container */
.gradio-chatbot, .chatbot {
    background:#fbfaf8 !important;
    border:3px solid #804e49 !important;
    border-radius:25px !important;
    --border-color-primary: transparent !important;
    --chatbot-border-color: transparent !important;
    --panel-border-color: transparent !important;
}

/* ⚡ VERTICAL LINE OVERRIDES ⚡ */
.gradio-chatbot *, 
.gradio-chatbot div, 
.gradio-chatbot span, 
.gradio-chatbot blockquote,
.gradio-chatbot [class*="message"] {
    border: none !important;
    border-left: none !important;
    border-right: none !important;
    border-top: none !important;
    border-bottom: none !important;
    border-inline-start: none !important;
    border-inline-end: none !important;
    outline: none !important;
    box-shadow: none !important;
    background-image: none !important; 
}

/* Strips background fills from dynamic layout pseudo-elements */
.gradio-chatbot *::before, 
.gradio-chatbot *::after {
    background: transparent !important;
    background-color: transparent !important;
    background-image: none !important;
    border: none !important;
    border-left: none !important;
    border-inline-start: none !important;
    box-shadow: none !important;
}

/* Textbox */
textarea, input {
    background:#fbfaf8 !important;
    color:#0a122a !important;
    border:2px solid #804e49 !important;
    border-radius:15px !important;
}
/* Buttons */
.button-row {
    display:flex !important;
    justify-content:center !important;
    gap:25px !important;
}
button {
    background:#698f3f !important;
    color:#fbfaf8 !important;
    border-radius:15px !important;
    padding:12px 40px !important;
    font-size:18px !important;
}
button span {
    color:#fbfaf8 !important;
}
button:hover {
    opacity:0.85;
}""")

# --------------------------------------------------------------------
# KNOWLEDGE BASE & PIPELINE SETUP (RUNS AFTER DEMO LAUNCH CLOSES)
# --------------------------------------------------------------------

# 1. READ YOUR FILE
with open("knowledge.txt", "r", encoding="utf-8") as file:
    raw_text = file.read()

# 2. CHUNK BY YOUR UNDERSCORE SEPARATORS
text_chunks = [chunk.strip() for chunk in raw_text.split("________________") if chunk.strip()]
knowledge_base = Dataset.from_dict({"text": text_chunks})

# 3. CREATE THE TEXT SPACE
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
def embed_text(batch):
    return {"embeddings": embedding_model.encode(batch["text"])}

knowledge_base = knowledge_base.map(embed_text, batched=True)
knowledge_base.add_faiss_index(column="embeddings")

# 4. CHOOSE A TEST QUESTION
student_question = "My grades are dropping, what should I do?"

# 5. FIND THE BEST PARAGRAPH
question_vector = embedding_model.encode(student_question)
scores, retrieved_data = knowledge_base.get_nearest_examples("embeddings", question_vector, k=1)
retrieved_context = retrieved_data["text"]

# 6. GENERATE THE ANSWER
generator = pipeline("text-generation", model="HuggingFaceH4/zephyr-7b-beta", device_map="auto")
prompt = f"""You are a warm, encouraging college advisor named Athena. Answer the question using the provided context.
Context: {retrieved_context}
Question: {student_question}
Answer:"""

final_output = generator(prompt, max_new_tokens=150, do_sample=False)
print(final_output[0]["generated_text"])