---
title: AI Text Summarizer
emoji: 📚
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: "5.38.0"
python_version: "3.11"
app_file: app.py
pinned: false
license: mit
---

# 📚 AI Text Summarizer using Groq

An AI-powered text summarization application built with **Gradio** and the **Groq API**.

## ✨ Features

- 📝 Summarize pasted text
- 📄 Upload PDF files
- 📃 Upload DOCX files
- 📑 Upload TXT files
- 🌐 Summarize website content from URLs
- 📏 Choose summary length (Short, Medium, Long)
- 📋 Choose output style (Bullet Points, Paragraph, Academic, Business)
- ⚡ Fast inference using Groq LLMs
- 🎨 User-friendly Gradio interface

---

## 🛠️ Technologies

- Python
- Gradio
- Groq API
- BeautifulSoup4
- Requests
- PyPDF
- python-docx

---

## 📂 Project Structure

```text
AI_Text_Summarizer/
│
├── app.py
├── requirements.txt
├── README.md
```

---

## 🔑 Environment Variable

Add the following Secret in your Hugging Face Space.

| Name | Value |
|------|-------|
| GROQ_API_KEY | Your Groq API Key |

In your Python code:

```python
import os
from groq import Groq

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)
```

---

## ▶️ Run Locally

```bash
pip install -r requirements.txt
python app.py
```

---

## 🚀 Deploy to Hugging Face

1. Create a new **Gradio Space**.
2. Upload all project files.
3. Add the `GROQ_API_KEY` Secret.
4. Commit the files.
5. Hugging Face will automatically install the dependencies and launch your app.

---

## 📷 Features

✅ Text Input

✅ File Upload

- PDF
- DOCX
- TXT

✅ URL Summarization

✅ Adjustable Summary Length

✅ Multiple Output Styles

---

## 📜 License

This project is released under the MIT License.