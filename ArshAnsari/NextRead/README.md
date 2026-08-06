---
title: NextRead
emoji: 📖
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 5.33.1
app_file: app.py
pinned: false
---

# 📚 NextRead — AI-Powered Semantic Book Recommender

> *“The right book at the right time can change a life. NextRead helps you find it.”*

[![Live Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Live%20Demo-blue)](https://huggingface.co/spaces/ArshAnsari/NextRead)

**NextRead** is a modern book recommendation app that uses the power of Large Language Models, semantic search, and emotion detection to connect you with books that match your mood, preferences, and curiosity.

## 🎥 Demo

![NextRead Demo](DEMO/DEMO.gif)

---

## 🚀 Overview

**NextRead** is an interactive web application built with **Gradio** and **LangChain**. It enables users to:

* Understand **natural language** book queries using LLMs.
* Retrieve relevant books through **semantic search** with MiniLM embeddings.
* Classify books as **Fiction** or **Non-Fiction** using **zero-shot learning**.
* Filter suggestions based on **emotional tone** like joy, sadness, or fear.
* Explore books via a **responsive UI** featuring animated, scrollable carousels.

---

## ✨ Features

### 🔍 Smart Semantic Search

Search using everyday language. Forget keywords—NextRead uses embeddings and cosine similarity to retrieve books that **match your intent**, not just your words.

> *Try: “heartwarming travel memoir with humor” or “dark, fast-paced thriller”.*

### 🏷️ Fiction vs. Non-Fiction Classification

Uses the `bart-large-mnli` model to instantly classify and filter books by type — **no pre-labeling needed**.

### 🎭 Emotion-Based Filtering

Detects the dominant **emotions** in each book description (joy, sadness, anger, etc.), helping you choose books that **match or shift your mood**.

### 🎨 Clean & Responsive Frontend

Built with **Gradio Blocks**, the UI is modular and mobile-friendly with interactive components like:

* Featured book **carousel**
* **Hover effects** for rich previews
* Clean layout optimized for engagement

---

## 🛠 Tech Stack

| Layer                | Technology                                 |
| -------------------- | ------------------------------------------ |
| **Embeddings**       | `all-MiniLM-L6-v2` (Sentence Transformers) |
| **Vector DB**        | Chroma (via LangChain)                     |
| **Classification**   | `facebook/bart-large-mnli` (Zero-shot)     |
| **Frontend**         | Gradio (Blocks API)                        |
| **NLP Backend**      | Hugging Face Transformers, Datasets        |
| **Data Handling**    | Pandas, NumPy                              |
| **Analysis & Plots** | Plotly (used in notebooks)                 |
| **Environment**      | Conda + `requirements.txt`                 |

---

## 📁 Folder Structure

```
NextRead/
├── app.py        # Main Gradio UI logic
├── data-exploration.ipynb     # Data cleaning and emotion tagging
├── vector-search.ipynb        # Embedding and similarity search
├── text-classification.ipynb  # Zero-shot category classification
├── sentiment-analysis.ipynb   # Emotion detection logic
├── books_with_emotions.csv    # Final dataset with emotions
├── requirements.txt           # Python dependencies
├── .env                       # API keys (excluded from version control)
└── README.md                  # Project documentation
```

---

## ⚙️ Setup Instructions

### Prerequisites

* Python 3.8 or above
* Optional: Hugging Face API token (for gated models)

### 1. Clone the Repository

```bash
git clone https://github.com/ArshhAnsari/NextRead.git
cd NextRead
```

### 2. Create Virtual Environment

```bash
conda create -n nextread python=3.10
conda activate nextread
```

### 3. Install Requirements

```bash
pip install -r requirements.txt
```

### 4. Add Hugging Face Token (Optional)

```bash
echo "HF_API_TOKEN=your_huggingface_token" > .env
```

### 5. Launch the App

```bash
python app.py
```

Then open `http://localhost:7860` in your browser.

---

## 🧭 Usage Guide

1. **Type a Query**

   > Ex: “uplifting fiction with emotional depth”

2. **Toggle Category**

   * Choose between Fiction or Non-Fiction

3. **Filter by Emotion**

   * Pick from joy, sadness, fear, surprise, anger

4. **Explore Results**

   * Scroll through rich previews with summaries and metadata

---

## 🙌 Acknowledgements

* 🤗 **Hugging Face** – Transformers & Datasets
* 🧠 **LangChain** – Simplified LLM orchestration
* 🧲 **Chroma** – High-speed vector store
* 🎛️ **Gradio** – No-fuss UI development

---

## 🤝 Contributing

All contributions are welcome!

* Open issues for bugs or feature requests
* Fork → Create a Branch → Submit a PR
* Star ⭐ the repo if you find it useful!

> **Books meet AI. Welcome to the future of reading.**

---

