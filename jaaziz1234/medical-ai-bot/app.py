import os
import traceback
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from langchain_pinecone import PineconeVectorStore
from langchain_core.prompts import ChatPromptTemplate
import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "medical-bot"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "medical_bot"))
from helper import download_hugging_face_embeddings
from langchain_google_genai import ChatGoogleGenerativeAI
import os

# Initialize Flask with explicit static and template settings
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app) 

load_dotenv()

# Ensure Pinecone API Key is set in the environment for PineconeVectorStore
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
if PINECONE_API_KEY:
    os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY
else:
    print("Warning: PINECONE_API_KEY is not set. Pinecone vector store may fail to initialize.")

INDEX_NAME = "medicalbot"
embeddings = download_hugging_face_embeddings()
docsearch = PineconeVectorStore.from_existing_index(
    index_name=INDEX_NAME,
    embedding=embeddings
)
retriever = docsearch.as_retriever(search_kwargs={"k": 4})
gemini_key = os.getenv("GEMINI_API_KEY") 
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.7,
    google_api_key=gemini_key
)
# Updated prompt to handle chat history for context memory
prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "You are an expert clinical medical assistant. Synthesize a concise and accurate answer using the provided multi-source retrieved context.\n"
        "Use the provided Chat History to understand the context of follow-up questions.\n"
        "If you don't know the answer or the context does not contain the information, say you don't know.\n"
        "CRITICAL: Always append this exact clinical disclaimer at the very end of your response on a new line: "
        "'[DISCLAIMER: This information is derived from verified global health reference materials and is for educational purposes only. Consult a professional physician for real medical interventions.]'\n\n"
        "Context:\n{context}\n\n"
        "Chat History:\n{history}"
    )),
    ("human", "{input}")
])

def helper_clean_source_name(raw_source):
    base_name = os.path.basename(raw_source).lower()
    if "gale" in base_name or "medical_book" in base_name:
        return "Gale Encyclopedia of Medicine"
    elif "medlineplus" in base_name:
        return "MedlinePlus Clinical Reference"
    elif "who" in base_name:
        return "WHO Global Health Framework"
    return "Verified Medical Reference Manual"

# 1. Root Route now serves the actual Frontend Chatbot!
@app.route('/', methods=['GET'])
def home():
    return render_template('chat.html')

# 2. API Endpoint
@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_question = data.get("question", "")
    
    # Extract chat history from the frontend payload
    raw_history = data.get("history", [])
    formatted_history = "\n".join([f"User: {msg.get('user', '')}\nBot: {msg.get('bot', '')}" for msg in raw_history])
    
    try:
        retrieved_docs = retriever.invoke(user_question)
        citations = []
        seen_citations = set()
        
        for doc in retrieved_docs:
            raw_src = doc.metadata.get("source", "Unknown Document")
            clean_src = helper_clean_source_name(raw_src)
            raw_page = doc.metadata.get("page_label") or doc.metadata.get("page") or "N/A"
            clean_page = str(int(float(raw_page))) if raw_page != "N/A" else "N/A"
            
            citation_string = f"{clean_src} (Page {clean_page})"
            if citation_string not in seen_citations:
                seen_citations.add(citation_string)
                citations.append({"book": clean_src, "page": clean_page})
        
        context_text = "\n\n".join(doc.page_content for doc in retrieved_docs)
        formatted_prompt = prompt.format_messages(
            context=context_text, 
            history=formatted_history, 
            input=user_question
        )
        ai_response = llm.invoke(formatted_prompt).content
        
        # Strict Citation Purging: If Gemini admits it doesn't know, clear the sources
        response_lower = ai_response.lower()
        if "do not know" in response_lower or "don't know" in response_lower:
            citations = []
        
        return jsonify({
            "status": "success",
            "answer": ai_response,
            "citations": citations
        })
    except Exception as e:
        print(f"[Error] {traceback.format_exc()}")
        return jsonify({"status": "error", "message": str(e)}), 500
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860, debug=True)
