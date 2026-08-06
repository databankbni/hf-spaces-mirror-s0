import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_groq import ChatGroq

load_dotenv()

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHROMA_DIR = "chroma_db"

embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
    groq_api_key=os.getenv("GROQ_API_KEY")
)

vectorstore = None


def process_pdfs(file_paths):
    """Loads PDFs, splits into 500-char chunks with 100 overlap, embeds, and stores in ChromaDB."""
    global vectorstore
    all_chunks = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)

    for path in file_paths:
        loader = PyPDFLoader(path)
        pages = loader.load()
        doc_name = os.path.basename(path)
        for page in pages:
            page.metadata["source"] = doc_name  # keep the filename attached to every page
        chunks = splitter.split_documents(pages)
        all_chunks.extend(chunks)

    vectorstore = Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DIR,
    )
    return f"✅ Indexed {len(all_chunks)} chunks from {len(file_paths)} document(s)."


def answer_question(question):
    """Answers a question using only retrieved chunks, with a document + page citation."""
    if vectorstore is None:
        return "⚠️ Please upload and process your documents first."

    docs = vectorstore.similarity_search(question, k=4)
    if not docs:
        return "I couldn't find anything about that in your uploaded documents."

    context = "\n\n".join(
        f"[Source: {d.metadata.get('source', 'unknown')}, Page {d.metadata.get('page', 0) + 1}]\n{d.page_content}"
        for d in docs
    )

    prompt = f"""You are a study assistant. Answer the student's question using ONLY the context below.
If the context does not contain the answer, say clearly that the uploaded documents don't cover it. Never make anything up.

Context:
{context}

Question: {question}

Give a clear answer, then end with a new line exactly like:
Sources: <document name> (page <number>)"""

    response = llm.invoke(prompt)
    return response.content


def get_relevant_chunks(topic, k=3):
    """Used later by the revision engine to re-retrieve chunks about a specific weak topic."""
    if vectorstore is None:
        return []
    return vectorstore.similarity_search(topic, k=k)
    