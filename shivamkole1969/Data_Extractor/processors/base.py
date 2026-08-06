"""
Base Processor - Abstract base class for all report type processors.
All new report types must extend this class and implement the `process()` method.

To add a new report type:
1. Create a new file in processors/ (e.g., processors/NEW_TYPE.py)
2. Create a class extending BaseProcessor
3. Implement the `process(pdf_path, job)` method
4. Register it in processors/registry.py
"""

import time
import traceback
import re
import json
from datetime import datetime
from pathlib import Path
from abc import ABC, abstractmethod

from groq import Groq


class BaseProcessor(ABC):
    """Abstract base class for all report processors."""
    
    # Override these in subclasses
    PROCESSOR_NAME = "Base"
    SUPPORTED_EXTENSIONS = [".pdf"]
    
    def __init__(self, api_keys: list, output_folder: Path):
        self.api_keys = api_keys
        self.output_folder = output_folder
        self._key_index = 0
    
    def get_groq_client(self) -> Groq:
        """Get a Groq client with automatic key rotation."""
        if not self.api_keys:
            raise ValueError("No API keys available. Check api_keys.txt")
        key = self.api_keys[self._key_index % len(self.api_keys)]
        self._key_index += 1
        return Groq(api_key=key)
    
    def call_llm(self, prompt: str, max_tokens: int = 4000, temperature: float = 0.1) -> str:
        """Make an LLM call with error handling and key rotation."""
        client = self.get_groq_client()
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[{self.PROCESSOR_NAME}] LLM error: {e}")
            # Try with next key
            client = self.get_groq_client()
            try:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content.strip()
            except Exception as e2:
                print(f"[{self.PROCESSOR_NAME}] LLM retry failed: {e2}")
                return ""
    
    def extract_json_array(self, text: str) -> list:
        """Extract a JSON array from LLM response text."""
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return []
    
    def extract_json_object(self, text: str) -> dict:
        """Extract a JSON object from LLM response text."""
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}
    
    def run(self, filepath: str, job):
        """Main entry point - wraps process() with error handling."""
        job.status = "processing"
        job.message = f"Starting {self.PROCESSOR_NAME} processing..."
        job.start_time = time.time()
        
        try:
            output_file = self.process(filepath, job)
            if output_file:
                job.output_file = output_file
        except Exception as e:
            job.status = "error"
            job.error = traceback.format_exc()
            job.message = f"Error: {str(e)}"
            job.end_time = time.time()
            traceback.print_exc()
            raise e
    
    @abstractmethod
    def process(self, filepath: str, job):
        """
        Process a report file and generate Excel output.
        Must be implemented by each processor.
        
        Args:
            filepath: Path to the input file (PDF, Excel, etc.)
            job: ProcessingJob instance to update progress/status
        """
        raise NotImplementedError("Subclasses must implement process()")
