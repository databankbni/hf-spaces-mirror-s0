import json
import re
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv
from rag_engine import get_relevant_chunks

load_dotenv()

quiz_history = []  # remembers every quiz attempt made during this session

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,
    groq_api_key=os.getenv("GROQ_API_KEY")
)


def _extract_json(text):
    """Groq sometimes wraps JSON in ```json fences or extra text — this strips that off."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    return json.loads(text)


def generate_quiz(vectorstore):
    """Generates 10 questions (5 MCQ + 5 short-answer) sourced ONLY from the uploaded docs."""
    if vectorstore is None:
        return None, "⚠️ Please upload and process your documents first."

    sample_docs = vectorstore.similarity_search("summary overview key concepts", k=8)
    context = "\n\n".join(d.page_content for d in sample_docs)

    prompt = f"""Based ONLY on the study material below, generate a quiz with EXACTLY 10 questions:
- 5 multiple choice questions (4 options each, one correct)
- 5 short-answer questions

Do NOT use any outside knowledge. Every question must be answerable from the material below.

Study material:
{context}

Respond with ONLY valid JSON, no other text, in exactly this format:
{{
  "questions": [
    {{"id": 1, "type": "mcq", "topic": "short topic name", "question": "...", "options": ["A", "B", "C", "D"], "answer": "A"}},
    {{"id": 6, "type": "short", "topic": "short topic name", "question": "...", "answer": "expected answer"}}
  ]
}}"""

    response = llm.invoke(prompt)
    try:
        quiz_data = _extract_json(response.content)
        return quiz_data, "✅ Quiz generated!"
    except Exception as e:
        return None, f"⚠️ Couldn't parse quiz, please try generating again. ({e})"


def grade_quiz(quiz_data, user_answers):
    """Compares user answers to correct answers, returns score + list of missed topics."""
    missed_topics = []
    score = 0
    total = len(quiz_data["questions"])

    for q in quiz_data["questions"]:
        user_ans = user_answers.get(str(q["id"]), "").strip().lower()
        correct_ans = str(q["answer"]).strip().lower()

        if q["type"] == "mcq":
            is_correct = user_ans == correct_ans
        else:
            # short answer: loose match, since wording can vary
            is_correct = correct_ans in user_ans or user_ans in correct_ans

        if is_correct:
            score += 1
        else:
            missed_topics.append(q["topic"])

    return score, total, list(set(missed_topics))


def generate_revision_summary(vectorstore, weak_topics):
    """For each weak topic, re-retrieve chunks and write a focused 2-paragraph summary."""
    if not weak_topics:
        return "🎉 No weak topics — great job, you got everything right!"

    summaries = []
    for topic in weak_topics:
        chunks = get_relevant_chunks(topic, k=3)
        context = "\n\n".join(c.page_content for c in chunks)

        prompt = f"""Write a focused 2-paragraph revision summary about "{topic}" using ONLY the material below.
Do not add any outside facts. Be clear and student-friendly.

Material:
{context}"""

        response = llm.invoke(prompt)
        summaries.append(f"### 📌 {topic}\n\n{response.content}")

    return "\n\n---\n\n".join(summaries)


def log_quiz_attempt(score, total, missed_topics):
    """Saves this quiz attempt into memory so we can spot repeat-weak-topics later."""
    quiz_history.append({
        "attempt": len(quiz_history) + 1,
        "score": score,
        "total": total,
        "missed_topics": missed_topics,
    })
    return quiz_history


def get_topic_trends():
    """Looks across every attempt this session and finds topics missed more than once."""
    topic_counts = {}
    for attempt in quiz_history:
        for topic in attempt["missed_topics"]:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

    recurring = [(topic, count) for topic, count in topic_counts.items() if count > 1]
    recurring.sort(key=lambda x: x[1], reverse=True)
    return recurring


def format_progress_report():
    """Builds a readable text summary of quiz history + recurring weak topics."""
    if not quiz_history:
        return "No quiz attempts yet this session. Take a quiz first!"

    lines = ["### 📊 Your Session History\n"]
    for a in quiz_history:
        lines.append(f"- Attempt {a['attempt']}: {a['score']}/{a['total']} correct")

    trends = get_topic_trends()
    lines.append("\n### 🔁 Topics You Keep Missing\n")
    if trends:
        for topic, count in trends:
            lines.append(f"- **{topic}** — missed {count} times")
    else:
        lines.append("Nothing repeats yet — keep taking quizzes to build a trend!")

    return "\n".join(lines)
