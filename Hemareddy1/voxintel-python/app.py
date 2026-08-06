"""
VoxIntel Python NLP Service
Flask API that provides AI-assisted endpoints:
  - /parse-resume       : Extract skills, projects, etc. from resume text
  - /evaluate-answer    : Semantic evaluation of interview answers
  - /analyze-confidence : Confidence analysis from text patterns
  - /check-plagiarism   : Plagiarism and AI-content detection
  - /generate-followup  : Adaptive follow-up question based on keyword coverage
  - /generate-coding-questions : Select coding problems (60% static, 40% skill-matched)
  - /generate-code-followup : Adaptive follow-up for a coding submission (Coding Interview only)

Run with: python app.py (starts on port 5001)
"""

import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import logging

load_dotenv()

# Import our service modules
from resume_parser import parse_resume_file
from semantic_evaluator import evaluate_answer
from confidence_analysis import analyze_confidence
from plagiarism_checker import check_plagiarism
from feedback_generator import generate_feedback
from question_generator import generate_interview_questions, get_company_context
from resume_intelligence import generate_intelligence
from hybrid_question_generator import generate_hybrid_questions
from followup_generator import generate_followup_question
from coding_question_generator import generate_coding_questions
from code_followup_generator import generate_code_followup

# ── Flask Setup ─────────────────────────────────────────────

app = Flask(__name__)
CORS(app)  # Allow requests from the Node.js backend

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ── Routes ───────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "VoxIntel NLP Service"})


@app.route("/parse-resume", methods=["POST"])
def parse_resume():
    """
    Parse an uploaded resume file.
    Expects: multipart/form-data with 'file' and 'file_type' fields.
    Returns: structured JSON with skills, projects, education, etc.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    file_type = request.form.get("file_type", "pdf").lower()

    try:
        logger.info(f"Parsing resume: {file.filename} ({file_type})")
        result = parse_resume_file(file, file_type)

        # Phase 1: Generate intelligence report from parsed data
        intelligence = generate_intelligence(result)
        result["intelligence"] = intelligence

        return jsonify(result)
    except Exception as e:
        logger.error(f"Resume parse error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/evaluate-answer", methods=["POST"])
def evaluate():
    """
    Evaluate a user's interview answer against an ideal answer.
    Expects JSON: { user_answer, ideal_answer, keywords, answer_mode, time_taken }
    Returns: semantic_score, keyword_score, completeness_score, overall_score, feedback
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    user_answer = data.get("user_answer", "")
    ideal_answer = data.get("ideal_answer", "")
    keywords = data.get("keywords", [])
    answer_mode = data.get("answer_mode", "text")
    time_taken = data.get("time_taken", 0)

    if not user_answer:
        return jsonify({"error": "user_answer is required"}), 400

    try:
        logger.info("Evaluating answer...")

        # Step 1: Semantic + keyword evaluation
        eval_result = evaluate_answer(user_answer, ideal_answer, keywords)

        # Step 2: Confidence analysis (from text patterns). Only meaningful for
        # voice answers — filler words/hedging/pacing are communication signals
        # that don't apply to typed text, so a text answer gets no confidence
        # score at all (score: None) rather than a misleading number. Both the
        # client's confidence bar and generate_feedback()'s confidence
        # paragraph already skip rendering when score is None.
        if answer_mode == "voice":
            confidence_result = analyze_confidence(user_answer, time_taken, answer_mode)
        else:
            confidence_result = {
                "score": None,
                "filler_word_count": 0,
                "hedging_count": 0,
                "confidence_signal_count": 0,
                "speech_speed": None,
                "wpm": None,
                "time_flag": None,
                "feedback": None,
                "suggestions": [],
            }

        # Step 3: Plagiarism / AI detection
        plagiarism_result = check_plagiarism(user_answer, time_taken)

        # Step 4: Generate personalized feedback
        # Pass user_answer so the feedback can identify which specific keywords were missed
        feedback = generate_feedback(eval_result, confidence_result, plagiarism_result, keywords, user_answer)

        return jsonify({
            **eval_result,
            "confidence": confidence_result,
            "plagiarism": plagiarism_result,
            "feedback": feedback,
        })
    except Exception as e:
        logger.error(f"Evaluation error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/analyze-confidence", methods=["POST"])
def confidence_endpoint():
    """
    Standalone confidence analysis.
    Expects JSON: { text, time_taken, mode }
    """
    data = request.get_json()
    try:
        result = analyze_confidence(
            data.get("text", ""),
            data.get("time_taken", 0),
            data.get("mode", "text")
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/check-plagiarism", methods=["POST"])
def plagiarism_endpoint():
    """
    Standalone plagiarism check.
    Expects JSON: { text, time_taken }
    """
    data = request.get_json()
    try:
        result = check_plagiarism(
            data.get("text", ""),
            data.get("time_taken", 0)
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generate-questions", methods=["POST"])
def generate_questions_endpoint():
    """
    Generate personalized interview questions from resume data.
    Expects JSON: { skills, projects, company, role, interview_type, difficulty, count }
    Returns: list of generated question objects.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    try:
        questions = generate_interview_questions(
            skills=data.get("skills", []),
            projects=data.get("projects", []),
            company=data.get("company", "General"),
            role=data.get("role", "Software Engineer"),
            interview_type=data.get("interview_type", "Technical Interview"),
            difficulty=data.get("difficulty", "medium"),
            count=data.get("count", 10),
        )
        return jsonify({"questions": questions, "count": len(questions)})
    except Exception as e:
        logger.error(f"Question generation error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/analyze-intelligence", methods=["POST"])
def analyze_intelligence_endpoint():
    """
    Generate resume intelligence from an already-parsed resume dict.
    Expects JSON: { parsed: { skills, projects, experience, certifications, ... } }
    Returns: intelligence dict with candidateLevel, readinessScore, etc.
    Called by Node.js after loading an existing parsed resume from the DB.
    """
    data = request.get_json()
    if not data or "parsed" not in data:
        return jsonify({"error": "JSON body with 'parsed' field required"}), 400

    try:
        intelligence = generate_intelligence(data["parsed"])
        return jsonify(intelligence)
    except Exception as e:
        logger.error(f"Intelligence analysis error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/generate-questions-hybrid", methods=["POST"])
def generate_questions_hybrid_endpoint():
    """
    Generate a hybrid set of interview questions: 60% resume-based + 40% dataset.
    Expects JSON: {
        parsed: { skills, projects, experience, ... },  # parsed resume
        intelligence: { candidateLevel, readinessScore, ... },  # from /analyze-intelligence
        dataset_questions: [ ... ],   # questions from Node.js DB
        count: 10,
        interview_type: "Technical Interview"
    }
    Returns: { questions: [...], count: N, distribution: { resume: N, dataset: N } }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    parsed = data.get("parsed", {})
    intelligence = data.get("intelligence", {})
    dataset_questions = data.get("dataset_questions", [])
    count = int(data.get("count", 10))
    interview_type = data.get("interview_type", "Technical Interview")

    try:
        questions = generate_hybrid_questions(
            parsed=parsed,
            intelligence=intelligence,
            dataset_questions=dataset_questions,
            count=count,
            interview_type=interview_type,
        )

        resume_count = sum(1 for q in questions if q.get("source") == "resume")
        dataset_count = sum(1 for q in questions if q.get("source") == "dataset")

        return jsonify({
            "questions": questions,
            "count": len(questions),
            "distribution": {
                "resume": resume_count,
                "dataset": dataset_count,
            },
        })
    except Exception as e:
        logger.error(f"Hybrid question generation error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/generate-coding-questions", methods=["POST"])
def generate_coding_questions_endpoint():
    """
    Select a set of hands-on coding problems for a Coding Interview/Round
    session: 60% from the static bank, 40% prioritized toward the candidate's
    resume skills. Expects JSON: { skills: [...], count: 10 }
    Returns: { questions: [...], count: N }
    Each question includes hidden_test_cases — the Node caller must strip
    those before sending the response to the frontend, keeping them
    server-side for grading.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    try:
        questions = generate_coding_questions(
            skills=data.get("skills", []),
            count=int(data.get("count", 10)),
        )
        return jsonify({"questions": questions, "count": len(questions)})
    except Exception as e:
        logger.error(f"Coding question generation error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/generate-followup", methods=["POST"])
def generate_followup_endpoint():
    """
    Generate an adaptive follow-up question based on keyword coverage in
    the candidate's answer to the current question.
    Expects JSON: { user_answer, keywords }
    Returns: { question, based_on }
    Called by Node.js after evaluating a follow-up-eligible answer.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    try:
        result = generate_followup_question(
            data.get("user_answer", ""),
            data.get("keywords", []),
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Follow-up generation error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/generate-code-followup", methods=["POST"])
def generate_code_followup_endpoint():
    """
    Generate an adaptive follow-up question for a coding-round submission
    (Coding Interview sessions only — see sessionController.js).
    Expects JSON: { passed_count, total_count, expected_concepts, first_public_failure }
    `first_public_failure` (optional): { args, expected } from a *public*
    test case only — never pass hidden test case details here.
    Returns: { question, based_on }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    try:
        result = generate_code_followup(
            passed_count=int(data.get("passed_count", 0)),
            total_count=int(data.get("total_count", 0)),
            expected_concepts=data.get("expected_concepts", []),
            first_public_failure=data.get("first_public_failure"),
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Code follow-up generation error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/company-context", methods=["GET"])
def company_context_endpoint():
    """
    Get interview style notes for a specific company.
    Query param: ?company=Google
    """
    company = request.args.get("company", "General")
    try:
        context = get_company_context(company)
        return jsonify(context)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Start Server ─────────────────────────────────────────────

if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 5001))
    logger.info(f"🐍 VoxIntel NLP Service starting on port {port}...")
    app.run(host=host, port=port, debug=False)
