---
title: IFODA RAG
emoji: 🌱
colorFrom: green
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Agro-chemical knowledge base (RU/EN/UZ)
---

# IFODA RAG — Agro Chemical Knowledge Base

REST API + Web UI для поиска по продукции узбекско-японского СП **«Ifoda Agro Kimyo Himoya»**.
Отвечает на вопросы по пестицидам, удобрениям, дозировкам и защите растений на **RU / EN / UZ**.

> ⚠️ Агрохимия требует точности. Система отвечает **строго по документам** и всегда указывает источник.

## Endpoints

| Path | Метод | Что делает |
|---|---|---|
| `/`         | GET | Web UI (поисковая форма) |
| `/health`   | GET | `{"status":"ok","documents":946,"version":"1.1.0",...}` |
| `/query`    | POST | `{query, top_k?, use_llm?}` → ответ + цитаты + продукты |
| `/context`  | GET | `?q=...&top_k=5` → сырой контекст для внешнего LLM |
| `/docs`     | GET | Swagger UI |

## Пример вызова

```bash
curl -X POST https://L1679-ifoda-rag.hf.space/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Какой инсектицид против тли на хлопчатнике?", "top_k": 5}'
```

## Архитектура

```
Документы (Excel / DOCX / PDF)
   → ingest.py     → ChromaDB (946 чанков, cosine)
Запрос
   → retriever.py  → dense (e5-large-instruct) + sparse (BM25-like) + RRF
   → reranker      → cross-encoder BAAI/bge-reranker-v2-m3
   → query.py      → структурированный ответ с цитатами (+ опц. LLM)
   → server.py     → FastAPI на 0.0.0.0:7860
```

## Что внутри образа

- Python 3.11 (slim)
- `chromadb`, `sentence-transformers`, `torch` (CPU-only)
- Предзагруженные модели:
  - `intfloat/multilingual-e5-large-instruct` (embeddings, ~1.1 GB)
  - `BAAI/bge-reranker-v2-m3` (reranker, ~570 MB)
- Готовая `chroma_db/` (~8 MB, 946 чанков из 7 документов IFODA)
- Исходные Excel/DOCX/PDF — для переиндексации при cold start

## Замечание по ресурсам

HF Spaces **CPU basic** даёт 16 GB RAM — этого хватает для e5-large + bge-reranker с запасом.
Cold start ~30–60 сек (модели уже в образе), обычные запросы 1–3 сек.