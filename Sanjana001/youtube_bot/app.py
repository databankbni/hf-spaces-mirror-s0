import os
import gradio as gr
import requests
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEndpointEmbeddings, HuggingFaceEndpoint, ChatHuggingFace
from langchain_community.vectorstores import FAISS
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains import create_retrieval_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document

# Safe Environment configuration for your Llama model
os.environ["HUGGINGFACEHUB_API_TOKEN"] = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")

def run_rag_pipeline(video_url, question):
    try:
        # --- Step 1: Extract Video ID from URL ---
        video_id = None
        if "v=" in video_url:
            video_id = video_url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in video_url:
            video_id = video_url.split("youtu.be/")[1].split("?")[0]
        else:
            video_id = video_url.strip()
                
        if not video_id or len(video_id) < 11:
            return "Error: Invalid YouTube URL format. Please check the link."

        # --- Step 2: Fetch Transcript via Free Public AI-Proxy (Zero-Config) ---
        # Adding ?lang=en automatically pulls English, translating Hindi tracks if needed
        api_url = f"https://youtube-transcript.ai/transcript/{video_id}.txt?lang=en"
        
        try:
            response = requests.get(api_url)
            if response.status_code == 200:
                raw_text = response.text
            else:
                return f"Could not retrieve transcript from the proxy service. Status code: {response.status_code}"
                        
        except Exception as api_err:
            return f"Public connection failed: {str(api_err)}"

        if not raw_text.strip():
            return "Sorry, no transcript text could be retrieved for this video."

        # Wrap text safely into LangChain Document structure
        docs = [Document(page_content=raw_text, metadata={"source": video_url})]

        # --- Step 3: Split the Documents ---
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        split_docs = text_splitter.split_documents(docs)

        # --- Step 4: Vector Generation & Retrieval Assembly (Serverless Inference) ---
        embedding_model = HuggingFaceEndpointEmbeddings(
            model="sentence-transformers/all-MiniLM-L6-v2",
            huggingfacehub_api_token=os.getenv("HUGGINGFACEHUB_API_TOKEN")
        )
        vector_store = FAISS.from_documents(documents=split_docs, embedding=embedding_model)
        retriever = vector_store.as_retriever(search_kwargs={"k": 3})

        # --- Step 5: Large Language Model Configuration ---
        base_llm = HuggingFaceEndpoint(
            repo_id="meta-llama/Meta-Llama-3-8B-Instruct",
            task="text-generation",
            temperature=0.1,
            max_new_tokens=512
        )
        llm = ChatHuggingFace(llm=base_llm)

        system_prompt = (
            "You are an assistant specialized in answering questions about video transcripts.\n"
            "Use the following pieces of retrieved context from the transcript to answer "
            "the user's question. If you don't know the answer, say that you don't know.\n"
            "Keep the answer concise and accurate.\n\n"
            "Context:\n{context}"
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])

        # --- Step 6: Assemble Chain and Execute RAG Request ---
        question_answer_chain = create_stuff_documents_chain(llm, prompt)
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)
        
        response = rag_chain.invoke({"input": question})
        return response["answer"]

    except Exception as e:
        return f"Pipeline Error: {str(e)}"

# Gradio Dashboard Setup
demo = gr.Interface(
    fn=run_rag_pipeline,
    inputs=[
        gr.Textbox(label="YouTube URL", placeholder="Paste video link here..."),
        gr.Textbox(label="Question", placeholder="What do you want to know?")
    ],
    outputs=gr.Textbox(label="Answer Output"),
    title="🎬 YouTube Video RAG Assistant"
)

if __name__ == "__main__":
    demo.launch()