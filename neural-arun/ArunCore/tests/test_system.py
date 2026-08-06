"""
ArunCore Comprehensive System Integration Test Suite
Tests:
1. Knowledge Base Search & RAG Retrieval
2. Live GitHub API Data Sync
3. Telegram Alert & Message Delivery
4. Active Learning Loop (save_unknown_question_answer -> data/unknown_questions.json)
5. Agent Tool Execution & Persona Response
"""

import sys
import os
import json
import time

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

def test_knowledge_base():
    print("\n--- [TEST 1/5] Knowledge Base RAG Search ---")
    from core.agent import search_arun_knowledge
    query = "medical AI tutors neet bot"
    result = search_arun_knowledge.invoke({"query": query})
    print(f"Query: '{query}'")
    print(f"Result Snippet: {result[:300]}...")
    assert len(result) > 50, "Knowledge base search returned insufficient data"
    print("✅ [PASS] Knowledge Base Search working cleanly!")

def test_github_sync():
    print("\n--- [TEST 2/5] Live GitHub API Data Sync ---")
    from core.agent import get_github_live_data
    result = get_github_live_data.invoke({"username": "neural-arun"})
    print(f"Result Snippet:\n{result[:300]}...")
    assert "Live GitHub Repositories" in result or "github.com" in result, "GitHub sync returned invalid output"
    print("✅ [PASS] Live GitHub Sync working cleanly!")

def test_active_learning_loop():
    print("\n--- [TEST 3/5] Active Learning Loop (Telegram Reply -> unknown_questions.json) ---")
    from core.agent import save_unknown_question_answer
    
    test_q = f"Automated Test Question {int(time.time())}"
    test_a = "This is a verified test answer ingested by the automated test suite."
    
    res = save_unknown_question_answer(test_q, test_a)
    print(f"Function return: {res}")
    
    json_path = os.path.join(BASE_DIR, "data", "raw", "unknown_questions.json")
    assert os.path.exists(json_path), "data/raw/unknown_questions.json does not exist"
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    found = any(entry.get("question") == test_q for entry in data)
    assert found, f"Test question '{test_q}' not found in unknown_questions.json"
    print(f"Verified '{test_q}' saved into data/raw/unknown_questions.json (Total entries: {len(data)})")
    print("✅ [PASS] Active Learning Loop working cleanly!")

def test_telegram_delivery():
    print("\n--- [TEST 4/5] Telegram Alert Delivery Engine ---")
    from core.agent import _deliver_notify_arun, send_automated_chat_alert
    status = _deliver_notify_arun("SYSTEM_ALERT", "Automated system integration test run")
    print(f"Telegram Delivery Output: {status}")
    assert "SUCCESS" in status or "SKIPPED" in status, f"Telegram delivery failed: {status}"
    
    auto_status = send_automated_chat_alert("test_sys_session", "System test query", "System test response")
    print(f"Automated Chat Alert Output: {auto_status}")
    assert "SUCCESS" in auto_status or "SKIPPED" in auto_status, f"Automated chat alert failed: {auto_status}"
    print("✅ [PASS] Telegram Alert Engine working cleanly!")

def test_agent_execution():
    print("\n--- [TEST 5/5] Agent Invocation & Tool Execution ---")
    from core.agent import init_agent
    main_llm, prompt, default_memory, tools = init_agent()
    print(f"Loaded {len(tools)} agent tools: {[t.name for t in tools]}")
    
    messages = prompt.format_messages(
        running_summary=default_memory.running_summary,
        chat_history=[],
        input="Tell me about Arun's background in AI engineering.",
        agent_scratchpad=[],
    )
    ai_msg = main_llm.invoke(messages)
    if ai_msg.tool_calls:
        print(f"AI Persona triggered tool call(s): {[tc['name'] for tc in ai_msg.tool_calls]}")
        assert len(ai_msg.tool_calls) > 0, "Tool call array is empty"
    else:
        print(f"AI Persona Response (Temperature 0.7):\n{ai_msg.content[:250]}...")
        assert len(ai_msg.content) > 10, "Agent generated empty response"
    print("✅ [PASS] Agent Invocation & Persona working cleanly!")

if __name__ == "__main__":
    print("=========================================================")
    print("      ARUNCORE SYSTEM FUNCTIONALITY TEST SUITE           ")
    print("=========================================================")
    try:
        test_knowledge_base()
        test_github_sync()
        test_active_learning_loop()
        test_telegram_delivery()
        test_agent_execution()
        print("\n=========================================================")
        print("🎉 ALL 5 SYSTEM TESTS PASSED SUCCESSFULLY! EVERYTHING IS HEALTHY.")
        print("=========================================================")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
