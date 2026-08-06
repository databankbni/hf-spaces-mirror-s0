import json
import logging
import time
import os
from typing import List, Dict, Any
from groq import Groq

logger = logging.getLogger(__name__)

class RelevanceFilter:
    """Uses Groq API (Llama 3.3 70B) to classify reviews as relevant to music discovery/algorithms."""

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is missing from environment variables.")
            
        self.client = Groq(api_key=self.api_key)
        self.model = "llama-3.3-70b-versatile"
        self.batch_size = 20
        
    def process_batch(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Classify a batch of records."""
        if not records:
            return []

        # Map of temporary ID to record to pass to the prompt
        record_map = {str(i): rec for i, rec in enumerate(records)}
        
        prompt = (
            "You are a data classifier. I will provide a JSON object where the keys are IDs and the values are texts (Spotify reviews or comments).\n"
            "Your job is to classify whether EACH text discusses music discovery, recommendations, the Spotify algorithm, repetitive listening, Discover Weekly, personalization, genre variety, or similar themes.\n\n"
            "Return ONLY a valid JSON object mapping the exact same IDs to a dictionary with two keys:\n"
            "- 'relevant': boolean (true if it discusses the above themes, false if it discusses unrelated topics like billing, ads, login bugs, crashes, UI updates unrelated to discovery).\n"
            "- 'relevance_confidence': float between 0.0 and 1.0 representing your confidence.\n\n"
            "Do NOT include markdown formatting (like ```json), just return the raw JSON object.\n\n"
            "Input Texts:\n"
        )
        
        input_data = {}
        for rid, rec in record_map.items():
            # Truncate to save tokens and avoid context limits on very long posts
            input_data[rid] = rec.get('text', '')[:1000]
            
        prompt += json.dumps(input_data, ensure_ascii=False)
        
        try:
            # Sleep to respect Groq free tier rate limits (30 RPM typical)
            time.sleep(2.5) 
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.0
            )
            result_json = response.choices[0].message.content
            
            # Clean up the output in case the model added markdown despite instructions
            if result_json.startswith("```json"):
                result_json = result_json[7:-3].strip()
                
            classifications = json.loads(result_json)
            
            for rid, rec in record_map.items():
                cls = classifications.get(rid, {})
                rec['relevant'] = cls.get('relevant', False)
                rec['relevance_status'] = 'classified'
                # Groq might return integers instead of floats, or strings
                try:
                    rec['relevance_confidence'] = float(cls.get('relevance_confidence', 0.0))
                except (ValueError, TypeError):
                    rec['relevance_confidence'] = 0.0
                
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate limit" in err_str.lower():
                logger.error(f"Groq API rate limit exhausted: {e}")
                for rec in records:
                    rec['relevant'] = None
                    rec['relevance_confidence'] = None
                    rec['relevance_status'] = 'quota_exhausted'
            else:
                logger.error(f"Groq API batch failed: {e}")
                for rec in records:
                    rec['relevant'] = False
                    rec['relevance_confidence'] = 0.0
                    rec['relevance_status'] = 'classified'
                
        return records
