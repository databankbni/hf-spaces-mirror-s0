import gradio as gr
from huggingface_hub import InferenceClient
from sentence_transformers import SentenceTransformer
import torch



with open("Knowledge.txt", "r", encoding="utf-8") as file:
    knowledge = file.read()

gr.Interface

#Chunking

def preprocess_text(text):

    # Split using --- (recommended for your KB)
    chunks = [
        chunk.strip()
        for chunk in text.split("---")
        if chunk.strip()
    ]

    print(f"Loaded {len(chunks)} chunks")

    return chunks

model = SentenceTransformer("all-MiniLM-L6-v2")

#Create Embeddings

def create_embeddings(text_chunks):

    embeddings = model.encode(
        text_chunks,
        convert_to_tensor=True
    )

    print("Embedding shape:", embeddings.shape)

    return embeddings

#Preparing knowledge base

cleaned_chunks = preprocess_text(knowledge)

chunk_embeddings = create_embeddings(cleaned_chunks)

#Semantic search

def get_top_chunks(query, chunk_embeddings, text_chunks, top_k=3):

    query_embedding = model.encode(
        query,
        convert_to_tensor=True
    )

    query_embedding = query_embedding / query_embedding.norm()

    chunk_embeddings_normalized = (
        chunk_embeddings
        / chunk_embeddings.norm(dim=1, keepdim=True)
    )

    similarities = torch.matmul(
        chunk_embeddings_normalized,
        query_embedding
    )

    top_indices = torch.topk(
        similarities,
        k=top_k
    ).indices

    top_chunks = []

    for i in top_indices:
        top_chunks.append(text_chunks[i])

    return top_chunks


client = InferenceClient("Qwen/Qwen2.5-7B-Instruct", bill_to="kode-with-klossy")

#Chat function

def respond(message, history):

    top_results = get_top_chunks(
        message,
        chunk_embeddings,
        cleaned_chunks
    )

    context = "\n\n".join(top_results)

    messages = [

        {
            "role": "system",
            "content":
            f"""
You are Finly, an AI Financial Literacy Assistant.

Your goal is to give personalized financial guidance.

Before answering, decide whether you have enough information.

If important information is missing, DO NOT guess.
Instead, ask 1-3 short follow-up questions first.

Examples of things you may ask:
- Country
- Age or student status
- Income
- Monthly expenses
- Financial goal
- Timeframe
- Current savings
- Risk tolerance
- Existing debt
- Employment status

Only answer after you have enough information.

Answer ONLY using the context below.

If the context does not contain the answer, say:

"I don't have enough information in my knowledge base to answer that."

Be friendly, conversational, and easy for students to understand.

If the user's request requires additional information to provide personalized guidance, ask ONE relevant follow-up question before giving detailed recommendations.

Always end every response with ONE relevant follow-up question.

The follow-up question should:
- Help personalize future guidance.
- Be short and conversational.
- Ask only ONE question at a time.
- Never repeat information the user has already shared.
- Be relevant to the current topic.

Examples:
• Budgeting → Ask about income or expenses.
• Investing → Ask about country, investment amount, or goals.
• Scholarships → Ask about country, university, or major.
• Credit Cards → Ask about country or age.

If you already have enough information, answer normally and still end with one helpful follow-up question.

You do not save your chat history or store personal account details. Remind users that all sessions are temporary.


Context:

{context}
"""
        }

    ]

    if history:
        messages.extend(history)

    messages.append(
        {
            "role": "user",
            "content": message
        }
    )

    response = client.chat.completions.create(

        model="Qwen/Qwen2.5-7B-Instruct",

        messages=messages,

        max_tokens=300,

    )

    return response.choices[0].message.content



css = """
.gradio-container {
    background: #AED6FC;
}

footer {
    display: none !important;
}
"""

with gr.Blocks(
    theme="harsh8001/cartoon-style",
    css=css
) as demo:

    gr.ChatInterface(
        fn=respond,
        title="💰 Finly",
        description="Your AI Financial Literacy Assistant",
    )

demo.launch()


