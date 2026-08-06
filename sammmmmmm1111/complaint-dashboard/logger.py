"""
Comprehensive Logging System for Smart Resolve Bot
Logs all agent executions, LLM interactions, database operations, and workflow events
"""
import csv
import os
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import threading


class LoggingSystem:
    """Centralized logging system for the entire Smart Resolve pipeline"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Define log file paths
        self.log_files = {
            'agent_execution': self.log_dir / 'agent_execution_log.csv',
            'llm_interactions': self.log_dir / 'llm_interactions.csv',
            'database_operations': self.log_dir / 'database_operations.csv',
            'workflow': self.log_dir / 'workflow_log.csv',
            'frontend_events': self.log_dir / 'frontend_events.csv',
            'errors': self.log_dir / 'error_log.csv',
            'performance': self.log_dir / 'performance_metrics.csv'
        }
        
        # Thread lock for safe concurrent writes
        self.lock = threading.Lock()
        
        # Initialize all CSV files with headers
        self._initialize_log_files()
        
        # Session tracking
        self.sessions = {}
    
    def _initialize_log_files(self):
        """Create log files with headers if they don't exist"""
        headers = {
            'agent_execution': [
                'timestamp', 'session_id', 'complaint_id', 'customer_id',
                'agent_name', 'input_summary', 'output_summary',
                'execution_time_ms', 'status', 'confidence'
            ],
            'llm_interactions': [
                'timestamp', 'complaint_id', 'agent', 'prompt_length',
                'model', 'tokens_input', 'tokens_output',
                'response_time', 'raw_response'
            ],
            'database_operations': [
                'timestamp', 'complaint_id', 'collection',
                'operation', 'document_id', 'fields_changed', 'status'
            ],
            'workflow': [
                'timestamp', 'complaint_id', 'stage', 'details'
            ],
            'frontend_events': [
                'timestamp', 'session_id', 'customer_id', 'page', 'event', 'details'
            ],
            'errors': [
                'timestamp', 'agent', 'complaint_id', 'exception', 'stacktrace', 'status'
            ],
            'performance': [
                'timestamp', 'complaint_id', 'classification_time_ms',
                'decision_time_ms', 'action_time_ms', 'verification_time_ms',
                'database_time_ms', 'rag_time_ms', 'total_pipeline_time_ms'
            ]
        }
        
        for log_type, file_path in self.log_files.items():
            if not file_path.exists():
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=headers[log_type])
                    writer.writeheader()
    
    def _append_to_csv(self, log_type: str, data: Dict[str, Any]):
        """Thread-safe append to CSV file"""
        with self.lock:
            try:
                with open(self.log_files[log_type], 'a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=list(data.keys()))
                    writer.writerow(data)
            except Exception as e:
                print(f"Logging error: {e}")
    
    def create_session(self, complaint_id: str, customer_id: str) -> str:
        """Create a new session for tracking a complaint lifecycle"""
        session_id = f"SID-{datetime.now().strftime('%Y%m%d%H%M%S')}-{complaint_id}"
        self.sessions[complaint_id] = session_id
        return session_id
    
    def get_session_id(self, complaint_id: str) -> str:
        """Get or create session ID for a complaint"""
        if complaint_id not in self.sessions:
            return self.create_session(complaint_id, "UNKNOWN")
        return self.sessions[complaint_id]
    
    # ========================================================================
    # AGENT EXECUTION LOGGING
    # ========================================================================
    
    def log_agent_execution(
        self,
        complaint_id: str,
        customer_id: str,
        agent_name: str,
        input_summary: str,
        output_summary: str,
        execution_time_ms: float,
        status: str,
        confidence: Optional[float] = None
    ):
        """Log agent execution"""
        session_id = self.get_session_id(complaint_id)
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'session_id': session_id,
            'complaint_id': complaint_id,
            'customer_id': customer_id,
            'agent_name': agent_name,
            'input_summary': input_summary[:500],  # Truncate for CSV
            'output_summary': output_summary[:500],
            'execution_time_ms': round(execution_time_ms, 2),
            'status': status,
            'confidence': confidence if confidence is not None else 'N/A'
        }
        
        self._append_to_csv('agent_execution', data)
    
    # ========================================================================
    # LLM INTERACTION LOGGING
    # ========================================================================
    
    def log_llm_interaction(
        self,
        complaint_id: str,
        agent: str,
        prompt: str,
        model: str,
        response: str,
        response_time_ms: float,
        tokens_input: int = 0,
        tokens_output: int = 0
    ):
        """Log LLM API calls"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'complaint_id': complaint_id,
            'agent': agent,
            'prompt_length': len(prompt),
            'model': model,
            'tokens_input': tokens_input,
            'tokens_output': tokens_output,
            'response_time': round(response_time_ms, 2),
            'raw_response': response[:1000]  # Truncate for CSV
        }
        
        self._append_to_csv('llm_interactions', data)
    
    # ========================================================================
    # DATABASE OPERATION LOGGING
    # ========================================================================
    
    def log_database_operation(
        self,
        complaint_id: str,
        collection: str,
        operation: str,  # READ, INSERT, UPDATE, DELETE
        document_id: str,
        fields_changed: Optional[Dict] = None,
        status: str = "SUCCESS"
    ):
        """Log database operations"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'complaint_id': complaint_id,
            'collection': collection,
            'operation': operation,
            'document_id': str(document_id),
            'fields_changed': json.dumps(fields_changed) if fields_changed else 'N/A',
            'status': status
        }
        
        self._append_to_csv('database_operations', data)
    
    # ========================================================================
    # WORKFLOW LOGGING
    # ========================================================================
    
    def log_workflow_stage(
        self,
        complaint_id: str,
        stage: str,
        details: str
    ):
        """Log workflow progression"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'complaint_id': complaint_id,
            'stage': stage,
            'details': details[:500]  # Truncate for CSV
        }
        
        self._append_to_csv('workflow', data)
    
    # ========================================================================
    # FRONTEND EVENT LOGGING
    # ========================================================================
    
    def log_frontend_event(
        self,
        session_id: str,
        customer_id: str,
        page: str,
        event: str,
        details: Optional[str] = None
    ):
        """Log frontend user interactions"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'session_id': session_id,
            'customer_id': customer_id,
            'page': page,
            'event': event,
            'details': details[:500] if details else 'N/A'
        }
        
        self._append_to_csv('frontend_events', data)
    
    # ========================================================================
    # ERROR LOGGING
    # ========================================================================
    
    def log_error(
        self,
        agent: str,
        complaint_id: str,
        exception: Exception,
        status: str = "ERROR"
    ):
        """Log exceptions and errors"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'agent': agent,
            'complaint_id': complaint_id,
            'exception': str(exception)[:500],
            'stacktrace': str(exception.__traceback__)[:1000] if hasattr(exception, '__traceback__') else 'N/A',
            'status': status
        }
        
        self._append_to_csv('errors', data)
    
    # ========================================================================
    # PERFORMANCE METRICS
    # ========================================================================
    
    def log_performance_metrics(
        self,
        complaint_id: str,
        classification_time_ms: float,
        decision_time_ms: float,
        action_time_ms: float,
        verification_time_ms: float,
        database_time_ms: float,
        rag_time_ms: float,
        total_pipeline_time_ms: float
    ):
        """Log performance metrics for the entire pipeline"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'complaint_id': complaint_id,
            'classification_time_ms': round(classification_time_ms, 2),
            'decision_time_ms': round(decision_time_ms, 2),
            'action_time_ms': round(action_time_ms, 2),
            'verification_time_ms': round(verification_time_ms, 2),
            'database_time_ms': round(database_time_ms, 2),
            'rag_time_ms': round(rag_time_ms, 2),
            'total_pipeline_time_ms': round(total_pipeline_time_ms, 2)
        }
        
        self._append_to_csv('performance', data)
    
    # ========================================================================
    # DECISION AGENT LOGGING
    # ========================================================================
    
    def log_decision_agent_reasoning(
        self,
        complaint_id: str,
        customer_id: str,
        classification: Dict,
        rag_documents: list,
        db_collections_queried: list,
        decision: str,
        confidence: float,
        reasoning_summary: str
    ):
        """Log Decision Agent reasoning (concise, no chain-of-thought)"""
        # This is logged as part of agent_execution with detailed input/output
        input_summary = (
            f"Classification: {classification.get('product')} / {classification.get('issue_subtype')} | "
            f"RAG Docs: {len(rag_documents)} | "
            f"DB Collections: {', '.join(db_collections_queried)}"
        )
        
        output_summary = (
            f"Decision: {decision} | "
            f"Confidence: {confidence} | "
            f"Reasoning: {reasoning_summary[:200]}"
        )
        
        self.log_agent_execution(
            complaint_id=complaint_id,
            customer_id=customer_id,
            agent_name="DecisionAgent",
            input_summary=input_summary,
            output_summary=output_summary,
            execution_time_ms=0,  # Will be updated by caller
            status="SUCCESS",
            confidence=confidence
        )
    
    # ========================================================================
    # ACTION AGENT LOGGING
    # ========================================================================
    
    def log_action_agent_execution(
        self,
        complaint_id: str,
        customer_id: str,
        action: str,
        success: bool,
        execution_time_ms: float,
        details: Optional[str] = None
    ):
        """Log individual action execution"""
        status = "SUCCESS" if success else "FAILED"
        
        input_summary = f"Action: {action}"
        output_summary = details if details else f"Status: {status}"
        
        self.log_agent_execution(
            complaint_id=complaint_id,
            customer_id=customer_id,
            agent_name="ActionAgent",
            input_summary=input_summary,
            output_summary=output_summary,
            execution_time_ms=execution_time_ms,
            status=status
        )
    
    # ========================================================================
    # VERIFICATION LOGGING
    # ========================================================================
    
    def log_verification_result(
        self,
        complaint_id: str,
        customer_id: str,
        checks: list,
        overall_status: str,
        execution_time_ms: float
    ):
        """Log verification agent results"""
        input_summary = f"Checks: {len(checks)}"
        output_summary = f"Status: {overall_status} | Checks: {', '.join([c['check'] for c in checks])}"
        
        self.log_agent_execution(
            complaint_id=complaint_id,
            customer_id=customer_id,
            agent_name="VerificationAgent",
            input_summary=input_summary,
            output_summary=output_summary,
            execution_time_ms=execution_time_ms,
            status=overall_status.upper()
        )


# Global logger instance
_logger = None

def get_logger() -> LoggingSystem:
    """Get or create the global logger instance"""
    global _logger
    if _logger is None:
        _logger = LoggingSystem()
    return _logger