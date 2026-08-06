import app.config
from app.core.indexer import Indexer
from app.core.retriever import Retriever
from app.core.llm_agent import LLM_Agent

class Personalized_RAG:
    def __init__(
        self,
        file_path: str,
        user_id: str = "terminal_user",
        persist_dir: str = "./chroma_db",
        urls: list = None
    ):
        self.user_id = user_id
        self.indexer = Indexer(file_path=file_path, persist_dir=persist_dir, urls=urls)
        self.vectorstore = None
        self.retriever = None
        self.agent = LLM_Agent()

        # Try to load existing vectorstore if available
        if self.indexer.is_indexed():
            print("📂 Loading existing index...")
            self.vectorstore = self.indexer.get_vectorstore()
            self.retriever = Retriever(self.vectorstore)
        else:
            print("⚠️ No existing index found. Call `.index()` to create one.")
        print("🚀 Personalized_RAG initialized.")

    def index(self):
        """Manually build or rebuild the vectorstore."""
        print("⚙️ Starting indexing process...")
        self.vectorstore = self.indexer.get_vectorstore()
        self.retriever = Retriever(self.vectorstore)
        print("✅ Indexing complete. System ready for queries.")

    def ask(self, question: str):
        """Ask a question after ensuring the system is indexed."""
        if not self.vectorstore:
            return "❌ No index found. Please run `.index()` before asking questions."
        docs_retrieved = self.retriever.retrieve(question)
        return self.agent.ask(self.user_id, question, docs_retrieved)


if __name__ == "__main__":
    rag = Personalized_RAG(file_path="user_information/")

    # Optional: trigger indexing manually
    if not rag.indexer.is_indexed():
        user_input = input("No index found. Would you like to build it now? (y/n): ").lower()
        if user_input == "y":
            rag.index()

    while True:
        question = input("You: ")
        if question.lower() in ["exit", "quit"]:
            print("Goodbye!")
            break

        answer = rag.ask(question)
        print("Assistant:", answer)
        print("-" * 50)
