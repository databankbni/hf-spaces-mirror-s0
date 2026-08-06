"""
Test script for the logging system
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from logger import get_logger

async def test_logging():
    """Test all logging functionality"""
    log_system = get_logger()
    
    # Create a test session
    complaint_id = "CMP-TEST123"
    customer_id = "CUST001"
    session_id = log_system.create_session(complaint_id, customer_id)
    print(f"Created session: {session_id}")
    
    # Test 1: Agent execution logging
    print("\n1. Testing agent execution logging...")
    log_system.log_agent_execution(
        complaint_id=complaint_id,
        customer_id=customer_id,
        agent_name="ClassificationAgent",
        input_summary="Test input: credit card lost",
        output_summary="Product: Credit Card, Subtype: Card Lost, Confidence: 0.95",
        execution_time_ms=150.5,
        status="SUCCESS",
        confidence=0.95
    )
    print("✅ Agent execution logged")
    
    # Test 2: LLM interaction logging
    print("\n2. Testing LLM interaction logging...")
    log_system.log_llm_interaction(
        complaint_id=complaint_id,
        agent="ClassificationAgent",
        prompt="Classify this complaint: My credit card was lost",
        model="llama3-8b-8192",
        response="Credit Card",
        response_time_ms=1200.5,
        tokens_input=150,
        tokens_output=20
    )
    print("✅ LLM interaction logged")
    
    # Test 3: Database operation logging
    print("\n3. Testing database operation logging...")
    log_system.log_database_operation(
        complaint_id=complaint_id,
        collection="complaints",
        operation="INSERT",
        document_id="DOC123",
        fields_changed={"status": "Open", "product": "Credit Card"},
        status="SUCCESS"
    )
    print("✅ Database operation logged")
    
    # Test 4: Workflow logging
    print("\n4. Testing workflow logging...")
    log_system.log_workflow_stage(complaint_id, "Complaint Received", "Via Web")
    log_system.log_workflow_stage(complaint_id, "Complaint Classified", "Product: Credit Card, Issue: Card Lost")
    log_system.log_workflow_stage(complaint_id, "Decision Made", "auto_resolve")
    log_system.log_workflow_stage(complaint_id, "Action Executed", "block_credit_card")
    log_system.log_workflow_stage(complaint_id, "Workflow Complete", "Status: Resolved")
    print("✅ Workflow stages logged")
    
    # Test 5: Frontend event logging
    print("\n5. Testing frontend event logging...")
    log_system.log_frontend_event(
        session_id=session_id,
        customer_id=customer_id,
        page="/complaints",
        event="Complaint Submitted",
        details="Credit card lost complaint submitted via web form"
    )
    print("✅ Frontend event logged")
    
    # Test 6: Decision agent logging
    print("\n6. Testing decision agent logging...")
    log_system.log_decision_agent_reasoning(
        complaint_id=complaint_id,
        customer_id=customer_id,
        classification={"product": "Credit Card", "issue_subtype": "Card Lost", "confidence": 0.95},
        rag_documents=[],
        db_collections_queried=["cards", "accounts", "transactions"],
        decision="auto_resolve",
        confidence=0.95,
        reasoning_summary="Database verification: Found 1 active credit card(s) - blocking required"
    )
    print("✅ Decision agent reasoning logged")
    
    # Test 7: Action agent logging
    print("\n7. Testing action agent logging...")
    log_system.log_action_agent_execution(
        complaint_id=complaint_id,
        customer_id=customer_id,
        action="block_credit_card",
        success=True,
        execution_time_ms=45.2,
        details="Blocked 1 credit card(s)"
    )
    print("✅ Action agent execution logged")
    
    # Test 8: Verification logging
    print("\n8. Testing verification logging...")
    log_system.log_verification_result(
        complaint_id=complaint_id,
        customer_id=customer_id,
        checks=[
            {"check": "status_updated", "passed": True},
            {"check": "decision_stored", "passed": True},
            {"check": "action_plan_stored", "passed": True}
        ],
        overall_status="verified",
        execution_time_ms=12.3
    )
    print("✅ Verification result logged")
    
    # Test 9: Error logging
    print("\n9. Testing error logging...")
    try:
        raise ValueError("Test error")
    except Exception as e:
        log_system.log_error(
            agent="TestAgent",
            complaint_id=complaint_id,
            exception=e,
            status="ERROR"
        )
    print("✅ Error logged")
    
    # Test 10: Performance metrics
    print("\n10. Testing performance metrics...")
    log_system.log_performance_metrics(
        complaint_id=complaint_id,
        classification_time_ms=150.5,
        decision_time_ms=200.3,
        action_time_ms=100.2,
        verification_time_ms=12.3,
        database_time_ms=50.1,
        rag_time_ms=80.5,
        total_pipeline_time_ms=593.9
    )
    print("✅ Performance metrics logged")
    
    print("\n" + "="*80)
    print("✅ ALL LOGGING TESTS PASSED!")
    print("="*80)
    print(f"\nLog files created in: {log_system.log_dir.absolute()}")
    print("\nLog files:")
    for log_type, file_path in log_system.log_files.items():
        if file_path.exists():
            with open(file_path, 'r') as f:
                lines = f.readlines()
                print(f"  {log_type}: {len(lines)} lines (including header)")

if __name__ == "__main__":
    asyncio.run(test_logging())