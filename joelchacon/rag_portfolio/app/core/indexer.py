import os
import numpy as np
from huggingface_hub import InferenceClient
from langchain_chroma import Chroma

class HFInferenceEmbeddings:
    """Wrapper to use Hugging Face Inference API as LangChain embeddings."""
    def __init__(self, model_name: str, hf_token: str, batch_size: int = 8):
        self.client = InferenceClient(api_key=hf_token)
        self.model_name = model_name
        self.batch_size = batch_size

    def _embed_text(self, text):
        res = self.client.feature_extraction(text, model=self.model_name)
        emb = np.array(res, dtype=float)
        if emb.ndim > 1:
            emb = emb[0]
        return emb

    def embed_documents(self, texts: list):
        embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i+self.batch_size]
            for text in batch:
                embeddings.append(self._embed_text(text))
        return embeddings

    def embed_query(self, text: str):
        return self._embed_text(text)


class Indexer:
    def __init__(
        self,
        file_path: str,
        urls: list = None,
        persist_dir: str = "./chroma_db",
        chunk_size: int = 250,
        chunk_overlap: int = 0,
        collection_name: str = "my_text_docs",
        hf_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        hf_token: str = None,
        batch_size: int = 8
    ):
        self.file_path = file_path
        self.urls = urls or []
        self.persist_dir = persist_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.collection_name = collection_name
        self.hf_model_name = hf_model_name
        self.hf_token = hf_token or os.environ.get("HF_TOKEN")
        self.batch_size = batch_size
        self.vectorstore = None
        self.embedding_model = None

    def is_indexed(self) -> bool:
        """Check if an existing vectorstore is already persisted."""
        return os.path.exists(self.persist_dir) and any(os.scandir(self.persist_dir))

    def load_model(self):
        if self.embedding_model is None:
            self.embedding_model = HFInferenceEmbeddings(
                model_name=self.hf_model_name,
                hf_token=self.hf_token,
                batch_size=self.batch_size
            )
        return self.embedding_model

    def load_and_split(self):
        """Load text files and URLs, then split into chunks."""
        from langchain_community.document_loaders import TextLoader, WebBaseLoader #these import are here to save pod memory
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        docs = []

        # Load local text files
        if os.path.isdir(self.file_path):
            for filename in os.listdir(self.file_path):
                full_path = os.path.join(self.file_path, filename)
                if os.path.isfile(full_path) and filename.lower().endswith(".txt"):
                    loader = TextLoader(full_path)
                    docs.extend(loader.load())
        elif os.path.isfile(self.file_path):
            loader = TextLoader(self.file_path)
            docs = loader.load()

        # Load from URLs
        for url in self.urls:
            try:
                loader = WebBaseLoader(url, headers={"User-Agent": "MyCustomAgent/1.0"})
                docs.extend(loader.load())
            except Exception as e:
                print(f"⚠️ Failed to load URL {url}: {e}")

        # Split into chunks
        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        return splitter.split_documents(docs)

    def build_vectorstore(self, docs_splits):
        """Build a new Chroma vectorstore and persist it."""
        vectorstore = Chroma.from_documents(
            documents=docs_splits,
            embedding=self.load_model(),
            collection_name=self.collection_name,
            persist_directory=self.persist_dir,
        )
        print("✅ Indexing completed and persisted.")
        self.vectorstore = vectorstore
        return vectorstore

    def get_vectorstore(self):
        """Return a Chroma vectorstore — either loads an existing one or builds a new one."""
        self.load_model()  # Ensure embedding model is initialized
        if self.is_indexed():
            print("📂 Loading existing index...")
            self.vectorstore = Chroma(
                collection_name=self.collection_name,
                persist_directory=self.persist_dir,
                embedding_function=self.embedding_model,
            )
        else:
            print("⚙️ Building new index...")
            docs_splits = self.load_and_split()
            self.vectorstore = self.build_vectorstore(docs_splits)

        return self.vectorstore
