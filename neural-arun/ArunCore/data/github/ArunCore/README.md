# ArunCore — Production Personal AI Assistant & Portfolio

> **GitHub Repository:** [https://github.com/neural-arun/ArunCore](https://github.com/neural-arun/ArunCore)  
> **Live Web Application:** [https://aruncore.vercel.app](https://aruncore.vercel.app)

ArunCore is an agentic, stateful personal AI twin built for **Arun Yadav** (AI Systems Architect specializing in Healthcare & Education).

---

## Key Features
- **100% Automated Telegram Alerts**: Every visitor interaction automatically sends a notification to Arun's phone.
- **1-Click Magic Link 3-Way Real Human Takeover**: Enables Arun to join ongoing web chat sessions live from Telegram via a 1-click magic link.
- **Vercel Serverless Egress Relay**: Routes Telegram API traffic through Vercel serverless routes (`/api/telegram`) to eliminate firewall timeouts.
- **Active Learning Vector Store**: Stores verified human answers from Telegram replies into `data/raw/unknown_questions.json` and re-indexes ChromaDB.
- **Zero-Hallucination RAG**: Dense vector retrieval + BM25 keyword search + Cohere V3 Reranker.
- **Dynamic Language Rules**: Responds in 100% articulate English for English queries, matching user tone cleanly.
