import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv

# Import the agent logic from core.agent
from core.agent import init_agent, answer_query

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
EVAL_SET_PATH = BASE_DIR / "data" / "test_set" / "eval_set.json"
REPORT_PATH = BASE_DIR / "data" / "test_set" / "evaluation_report.json"
DEBUG_DIR = BASE_DIR / "evaluation_debug"

def fuzzy_match(topic, answer):
    """
    Check if a topic sounds like it's in the answer.
    More lenient than strict substring.
    """
    topic_clean = topic.lower().strip()
    answer_clean = answer.lower().strip()
    
    # 1. Direct match
    if topic_clean in answer_clean:
        return True
    
    # 2. Key word subset check (if all significant words of a topic are in the answer)
    # This helps catch "RAG Pipelines" vs "AI pipelines for RAG"
    stop_words = {"and", "the", "a", "an", "is", "for", "vs", "to", "of", "with"}
    words = [w for w in topic_clean.split() if w not in stop_words]
    
    if not words: return False
    
    matches = sum(1 for w in words if w in answer_clean)
    # If 75% of the important words are there, count it as a pass
    if (matches / len(words)) >= 0.75:
        return True
        
    return False

def save_detailed_log(qid, question, answer, chunks, retrieval_pass, missing_topics):
    """Save a clean markdown file for manual human inspection of this specific interaction."""
    os.makedirs(DEBUG_DIR, exist_ok=True)
    filepath = DEBUG_DIR / f"{qid}.md"
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# Evaluation Log: {qid}\n\n")
        f.write(f"## Question\n{question}\n\n")
        f.write(f"## Status\n")
        f.write(f"- **Retrieval Mode:** {'PASS' if retrieval_pass else 'FAIL'}\n")
        f.write(f"- **Generation Mode:** {'PASS' if not missing_topics else 'FAIL'}\n")
        if missing_topics:
            f.write(f"- **Missing Topics:** {', '.join(missing_topics)}\n")
        f.write(f"\n## ArunCore Answer\n{answer}\n\n")
        f.write(f"## Retrieved Chunks (Final Top 5)\n")
        for i, doc in enumerate(chunks):
            f.write(f"### Chunk {i+1} | Source: {doc.metadata.get('source')}\n")
            f.write(f"```text\n{doc.page_content}\n```\n\n")

def run_evaluation():
    print("--- ArunCore Dual-Evaluation Pipeline (Fuzzy Match + Rate Limit Handling) ---")
    
    # 1. Initialize Agent
    print("Initializing Agent...")
    try:
        vectorstore, bm25_retriever, compressor, llm, prompt = init_agent()
    except Exception as e:
        print(f"Failed to initialize agent: {e}")
        return

    # 2. Load Eval Set
    if not EVAL_SET_PATH.exists():
        print(f"Eval set not found at {EVAL_SET_PATH}")
        return
        
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        eval_set = json.load(f)

    results = []
    passed_retrieval = 0
    passed_generation = 0
    total = len(eval_set)

    print(f"Starting evaluation of {total} questions...\n")

    for i, test in enumerate(eval_set):
        qid = test.get("id", f"Q{i}")
        question = test.get("question")
        expected_source = test.get("expected_source")
        expected_topics = test.get("expected_topics", [])

        print(f"[{i+1}/{total}] Evaluating {qid}: {question[:60]}...")

        # Execute Agent
        try:
            # We add a delay to satisfy the 10/min Cohere Trial Limit
            if i > 0:
                print(f"  (Rate limit cool-down: 6.5s)")
                time.sleep(6.5)
            
            response = answer_query(question, vectorstore, bm25_retriever, compressor, llm, prompt)
            answer = response["answer"]
            chunks = response["retrieved_chunks"]
        except Exception as e:
            print(f"  Error Querying Agent: {e}")
            results.append({
                "id": qid,
                "status": "ERROR",
                "error": str(e)
            })
            continue

        # --- Layer 1: Retrieval Check ---
        retrieval_pass = False
        if expected_source.startswith("static/"):
            retrieval_pass = True 
        else:
            for doc in chunks:
                source_meta = doc.metadata.get("source", "").lower()
                if expected_source.lower() in source_meta:
                    retrieval_pass = True
                    break
        
        if retrieval_pass: passed_retrieval += 1

        # --- Layer 2: Generation Check ---
        # Fuzzy match for topics
        missing_topics = []
        for topic in expected_topics:
            if not fuzzy_match(topic, answer):
                missing_topics.append(topic)
        
        generation_pass = len(missing_topics) == 0
        if generation_pass: passed_generation += 1

        # Log detailed human-readable file
        save_detailed_log(qid, question, answer, chunks, retrieval_pass, missing_topics)

        # Store result in summary list
        results.append({
            "id": qid,
            "retrieval": "PASS" if retrieval_pass else "FAIL",
            "generation": "PASS" if generation_pass else "FAIL",
            "missing": missing_topics
        })

    # 3. Final Report
    report = {
        "summary": {
            "total_questions": total,
            "retrieval_accuracy": f"{(passed_retrieval/total)*100:.2f}%",
            "generation_accuracy": f"{(passed_generation/total)*100:.2f}%",
        },
        "details": results
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4)

    print("\n" + "="*40)
    print("EVALUATION COMPLETE")
    print(f"Retrieval Accuracy: {report['summary']['retrieval_accuracy']}")
    print(f"Generation Accuracy: {report['summary']['generation_accuracy']}")
    print(f"Detailed logs saved to: {DEBUG_DIR}")
    print("="*40)

if __name__ == "__main__":
    run_evaluation()
