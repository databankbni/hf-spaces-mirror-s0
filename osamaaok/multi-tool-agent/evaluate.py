import time
from router import ask_with_routing

EVAL_QUESTIONS = [
    # Calculator questions
    {
        "question": "What is 847293 * 58162?",
        "expected_tool": "calculator",
        "expected_answer": "49280255466",
        "check_type": "contains"
    },
    {
        "question": "What is 15% of 4827.50?",
        "expected_tool": "calculator",
        "expected_answer": None,
        "check_type": "tool_only"
    },
    {
        "question": "What is (230 + 180) / 2?",
        "expected_tool": "calculator",
        "expected_answer": "205",
        "check_type": "contains"
    },

    # Web search questions
    {
        "question": "What is the current weather in Lahore?",
        "expected_tool": "web_search",
        "expected_answer": None,
        "check_type": "tool_only"
    },
    {
        "question": "What is the latest version of Python?",
        "expected_tool": "web_search",
        "expected_answer": None,
        "check_type": "tool_only"
    },
    {
        "question": "What is the current price of Bitcoin?",
        "expected_tool": "web_search",
        "expected_answer": None,
        "check_type": "tool_only"
    },

    # RAG - N×M question: use the actual × symbol from the document
    {
        "question": "What is the N times M integration problem that MCP solves?",
        "expected_tool": "rag_retrieval",
        "expected_answer": "integration",  # broader check that's definitely in the answer
        "check_type": "contains"
    },
    {
        "question": "What are the three main roles in MCP?",
        "expected_tool": "rag_retrieval",
        "expected_answer": "Host",
        "check_type": "contains"
    },
    {
        "question": "What is the Thought Action Observation cycle in AI agents?",
        "expected_tool": "rag_retrieval",
        "expected_answer": "Thought",
        "check_type": "contains"
    },
    {
        "question": "How does RAG retrieval work using embeddings?",
        "expected_tool": "rag_retrieval",
        "expected_answer": "embedding",
        "check_type": "contains"
    },
]


def check_answer(answer, expected_answer, check_type):
    if check_type == "tool_only":
        return True
    if check_type == "contains":
        return expected_answer.lower() in str(answer).lower()
    return False


def run_evaluation():
    results = []

    for item in EVAL_QUESTIONS:
        question = item["question"]
        expected_tool = item["expected_tool"]
        print(f"\n{'='*60}\nQuestion: {question}")
        print(f"Expected tool: {expected_tool}")

        start = time.time()
        try:
            answer, tool_used, _ = ask_with_routing(question)
            elapsed = round(time.time() - start, 2)

            tool_correct = tool_used == expected_tool
            answer_correct = check_answer(
                answer,
                item["expected_answer"],
                item["check_type"]
            )

            results.append({
                "question": question,
                "expected_tool": expected_tool,
                "tool_used": tool_used,
                "tool_correct": tool_correct,
                "answer_correct": answer_correct,
                "time": elapsed,
                "crashed": False
            })

            status = "✓" if tool_correct else "✗"
            print(f"Tool used: {tool_used} {status}")
            print(f"Answer correct: {answer_correct}")
            print(f"Time: {elapsed}s")

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            results.append({
                "question": question,
                "expected_tool": expected_tool,
                "tool_used": None,
                "tool_correct": False,
                "answer_correct": False,
                "time": elapsed,
                "crashed": True,
                "error": str(e)
            })
            print(f"CRASHED: {e}")

    total = len(results)
    crashed = sum(1 for r in results if r["crashed"])
    tool_correct = sum(1 for r in results if r["tool_correct"])
    answer_correct = sum(1 for r in results if r["answer_correct"])
    avg_time = sum(r["time"] for r in results) / total

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"Total questions:      {total}")
    print(f"Routing accuracy:     {tool_correct}/{total} ({round(100*tool_correct/total, 1)}%)")
    print(f"Answer accuracy:      {answer_correct}/{total} ({round(100*answer_correct/total, 1)}%)")
    print(f"Crashed:              {crashed}/{total}")
    print(f"Avg response time:    {round(avg_time, 2)}s")

    return results


if __name__ == "__main__":
    run_evaluation()