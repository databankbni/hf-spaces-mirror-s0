---
title: AYM RAG Classifier
emoji: ⚖️
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 4.0.0
python_version: "3.10"
app_file: app.py
pinned: false

---

# AYM Başvuru Sınıflandırma + Gerekçe (RAG)

Bu Space şunları yapar:

- BigBird tabanlı sınıflandırma: **kabul edilemez** / **esas (ihlal)** / **esas (ihlal yok)**
- Integrated Gradients ile en etkili cümleleri çıkarır
- Qdrant (local) vektör veritabanından ilgili kaynakları getirir
- Groq LLM ile kullanıcı dostu gerekçe üretir

## Gerekli dosyalar

Repo köküne şunları ekleyin:

- `CommonBodyLogRegTFIDF.pth`
- `tfidf_logreg_main.joblib`
- `tfidf_logreg_sub.joblib`
- `qdrant_db/` (klasör)

## Secrets

Space Settings → Secrets:

- `GROQ_API_KEY`: `gsk_...`

İsterseniz model adını değiştirmek için env var:

- `GROQ_MODEL` (default: llama-3.3-70b-versatile)

