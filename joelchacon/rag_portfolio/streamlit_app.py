import streamlit as st
import uuid
from app.core.personalized_rag import Personalized_RAG

# --------------------------
# Page Config
# --------------------------
st.set_page_config(page_title="Joel's Assistant", layout="wide")
st.title("Joel's Assistant (Direct Agent)")

# --------------------------
# Session Initialization
# --------------------------
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

if "conversation" not in st.session_state:
    st.session_state.conversation = []

if "rag" not in st.session_state:
    st.session_state.rag = Personalized_RAG(
        file_path="data/user_information",
        user_id=st.session_state.user_id,
        urls=["https://www.linkedin.com/in/joel-chacon-castillo-351bb4194/"]
    )

if "question_input" not in st.session_state:
    st.session_state.question_input = ""

# --------------------------
# Function to send a question
# --------------------------
def send_question():
    # Initialize conversation with system message if it's empty
    if not st.session_state.conversation:
        st.session_state.conversation.append({
            "role": "system",
            "content": "This assistant is to provide information to recruiters."
        })

    question = st.session_state.question_input
    if question:
        # Send question to RAG model
        answer = st.session_state.rag.ask(question)
        
        # Update conversation history
        st.session_state.conversation.append({"role": "user", "content": question})
        st.session_state.conversation.append({"role": "assistant", "content": answer})
        
        # Clear input box
        st.session_state.question_input = ""

# --------------------------
# Input box
# --------------------------
st.text_input("Ask me anything:", key="question_input", on_change=send_question)

# --------------------------
# Chat bubbles CSS (dark mode, wrapped text)
# --------------------------
st.markdown("""
<style>
.chat-area {
    background-color: #1E1E1E;
    padding: 15px;
    border-radius: 10px;
    max-height: 400px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;  /* normal column, we'll reverse in Python */
}

.user-msg {
    background-color: #4CAF50;
    color: white;
    padding: 10px;
    border-radius: 10px;
    margin: 5px;
    text-align: left;
    max-width: 40%;             
    font-size: 14px;
    word-wrap: break-word;      
    overflow-wrap: break-word;
    white-space: pre-wrap;      
    align-self: flex-end;
}

.assistant-msg {
    background-color: #333333;
    color: white;
    padding: 10px;
    border-radius: 10px;
    margin: 5px;
    text-align: left;
    max-width: 50%;             
    font-size: 14px;
    word-wrap: break-word;
    overflow-wrap: break-word;
    white-space: pre-wrap;
    align-self: flex-start;
}

.chat-container {
    width: 100%;
    display: block;
}
</style>
""", unsafe_allow_html=True)

# --------------------------
# Display conversation (newest messages on top)
# --------------------------
chat_placeholder = st.empty()

with chat_placeholder.container():
    st.markdown('<div class="chat-area" id="chat-area">', unsafe_allow_html=True)

    # Reverse messages in Python to show newest first
    for msg in reversed(st.session_state.conversation):
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-container"><div class="user-msg">{msg["content"]}</div></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-container"><div class="assistant-msg">{msg["content"]}</div></div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # Auto-scroll to top (newest message visible)
    st.markdown("""
    <script>
    var chatArea = document.getElementById('chat-area');
    if (chatArea) {
        chatArea.scrollTop = 0;
    }
    </script>
    """, unsafe_allow_html=True)

# --------------------------
# Optional: show source documents
# --------------------------
with st.expander("Source Documents"):
    if hasattr(st.session_state.rag.retriever, "last_retrieved_docs"):
        docs_retrieved = st.session_state.rag.retriever.last_retrieved_docs
    else:
        docs_retrieved = []

    for i, doc in enumerate(docs_retrieved, start=1):
        st.markdown(f"**Doc {i}:** {doc.page_content}")
