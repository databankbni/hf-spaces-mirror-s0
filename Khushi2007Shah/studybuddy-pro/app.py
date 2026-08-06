import gradio as gr
from rag_engine import process_pdfs, answer_question, vectorstore
import rag_engine
from quiz_engine import generate_quiz, grade_quiz, generate_revision_summary, log_quiz_attempt, format_progress_report

current_quiz = {"data": None}


def handle_upload(files):
    if not files:
        return "⚠️ Please upload at least one PDF."
    file_paths = [f.name for f in files]
    return process_pdfs(file_paths)


def handle_question(question):
    if not question.strip():
        return "⚠️ Please type a question."
    return answer_question(question)


def handle_generate_quiz():
    quiz_data, message = generate_quiz(rag_engine.vectorstore)
    if quiz_data is None:
        return message, gr.update(visible=False), {}
    current_quiz["data"] = quiz_data

    # Build a readable display of the quiz for the student
    display_text = ""
    for q in quiz_data["questions"]:
        display_text += f"**Q{q['id']} ({q['type'].upper()}):** {q['question']}\n"
        if q["type"] == "mcq":
            for opt in q["options"]:
                display_text += f"- {opt}\n"
        display_text += "\n"

    return message, gr.update(visible=True, value=display_text), quiz_data


def handle_grade(answers_text):
    quiz_data = current_quiz["data"]
    if quiz_data is None:
        return "⚠️ Please generate a quiz first.", ""

    # answers_text format expected: one answer per line, e.g.
    # 1: A
    # 2: Paris
    user_answers = {}
    for line in answers_text.strip().split("\n"):
        if ":" in line:
            qid, ans = line.split(":", 1)
            user_answers[qid.strip()] = ans.strip()

    score, total, missed_topics = grade_quiz(quiz_data, user_answers)
    result_text = f"### Score: {score}/{total}\n\n"
    if missed_topics:
        result_text += f"**Weak topics:** {', '.join(missed_topics)}"
    else:
        result_text += "🎉 Perfect score!"
    log_quiz_attempt(score, total, missed_topics)


    revision = generate_revision_summary(rag_engine.vectorstore, missed_topics)

    return result_text, revision


with gr.Blocks(title="StudyBuddy Pro") as demo:
    gr.Markdown("# 📚 StudyBuddy Pro\nAI Study Assistant with RAG — turn passive notes into active recall.")

    with gr.Tab("1. Upload Notes"):
        file_upload = gr.File(file_count="multiple", file_types=[".pdf"], label="Upload your PDF notes")
        upload_btn = gr.Button("Process Documents", variant="primary")
        upload_status = gr.Textbox(label="Status", interactive=False)
        upload_btn.click(handle_upload, inputs=file_upload, outputs=upload_status)

    with gr.Tab("2. Ask Questions"):
        question_box = gr.Textbox(label="Ask a question about your notes")
        ask_btn = gr.Button("Get Answer", variant="primary")
        answer_box = gr.Textbox(label="Answer (with citation)", interactive=False, lines=6)
        ask_btn.click(handle_question, inputs=question_box, outputs=answer_box)

    with gr.Tab("3. Quiz Yourself"):
        gen_quiz_btn = gr.Button("Generate 10-Question Quiz", variant="primary")
        quiz_status = gr.Textbox(label="Status", interactive=False)
        quiz_display = gr.Markdown(visible=False)
        quiz_state = gr.State({})

        gr.Markdown("**How to answer:** type one answer per line like `1: A` or `6: Paris`, then submit below.")
        answers_input = gr.Textbox(label="Your answers", lines=10, placeholder="1: A\n2: C\n3: your short answer here...")
        grade_btn = gr.Button("Submit Answers", variant="primary")
        score_display = gr.Markdown()
        revision_display = gr.Markdown()

        gen_quiz_btn.click(handle_generate_quiz, outputs=[quiz_status, quiz_display, quiz_state])
        grade_btn.click(handle_grade, inputs=answers_input, outputs=[score_display, revision_display])

        gr.Markdown("---")
        progress_btn = gr.Button("📊 Show My Progress Across Attempts")
        progress_display = gr.Markdown()
        progress_btn.click(format_progress_report, outputs=progress_display)

if __name__ == "__main__":
    demo.launch()
    