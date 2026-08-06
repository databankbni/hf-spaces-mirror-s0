FROM python:3.12-slim

WORKDIR /app

COPY BankingAgent.py ./
COPY hf_web.py ./

RUN pip install --no-cache-dir flask groq requests beautifulsoup4 langchain-core langchain-community langchain-text-splitters langchain-huggingface sentence-transformers

EXPOSE 7860

CMD ["python", "hf_web.py"]