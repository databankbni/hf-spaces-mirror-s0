import os
import re
from .config import GOOGLE_API_KEY, MODEL_PRIORITY_LIST
from .prompts import get_master_prompt

class MagiSystem:
    def __init__(self):
        # Master Agent (Gemini) for Synthesis
        # We will initialize the client dynamically or check for key
        self.client = None
        if GOOGLE_API_KEY:
            try:
                from google import genai
                self.client = genai.Client(api_key=GOOGLE_API_KEY)
            except ImportError:
                print("Warning: google-genai not installed. Please install it.")
        
    def conduct_conference(self, user_question):
        """
        Executes the *New* Magi Process (Single-Shot):
        1. Construct a massive prompt simulating all 3 personas + synthesis.
        2. Call Gemini ONCE.
        3. Parse the result into the expected dictionary format.
        """
        
        # 0. Check Client
        if not self.client:
             if GOOGLE_API_KEY:
                try:
                    from google import genai
                    self.client = genai.Client(api_key=GOOGLE_API_KEY)
                except:
                    pass
            
             if not self.client:
                return {
                    "responses": {
                        "Melchior": {"status": "Error", "reasoning": "API Key Missing"},
                        "Balthasar": {"status": "Error", "reasoning": "API Key Missing"},
                        "Casper": {"status": "Error", "reasoning": "API Key Missing"}
                    },
                    "synthesis": "System Error: GOOGLE_API_KEY missing or not configured."
                }

        # 1. Generate Prompt
        prompt = get_master_prompt(user_question)
        full_text = ""

        # 2. Call Gemini (with model fallback)
        last_error = "Unknown Error"
        
        import time
        import re

        for model_name in MODEL_PRIORITY_LIST:
            # Clean model name
            clean_name = model_name.replace("models/", "")
            
            # Retry loop for the SAME model (up to 3 times)
            for attempt in range(3):
                try:
                    print(f"Attempting model: {clean_name} (Attempt {attempt+1})")
                    response = self.client.models.generate_content(
                        model=clean_name,
                        contents=prompt,
                        config={
                            'response_mime_type': 'text/plain'
                        }
                    )
                    full_text = response.text
                    break # Success inside retry loop
                    
                except Exception as e:
                    error_str = str(e)
                    last_error = error_str
                    print(f"Error with {clean_name}: {error_str}")
                    
                    # Check for Rate Limit (429) or Quota
                    if "429" in error_str or "quota" in error_str.lower() or "RESOURCE_EXHAUSTED" in error_str:
                        # Try to parse "retry in X seconds"
                        wait_time = 5 * (2 ** attempt) # Default backoff: 5s, 10s, 20s
                        
                        match = re.search(r"retry in (\d+\.?\d*)s", error_str)
                        if match:
                            suggested_wait = float(match.group(1))
                            wait_time = max(wait_time, suggested_wait + 1) # Add buffer
                        
                        print(f"Rate limit hit. Waiting {wait_time:.1f}s before retrying...")
                        time.sleep(wait_time)
                        continue # Retry the same model
                    else:
                        # Non-retriable error (e.g. 404, 400), break retry loop and try next model
                        break
            
            if full_text:
                break # Success in main loop
            
            # If we are here, the model failed 3 times or had a non-retriable error.
            # Continue to next model in priority list.
        
        if not full_text:
            error_msg = f"Generation Failed. Last Error: {last_error}"
            return {
                "responses": {
                    "Melchior": {"status": "Error", "reasoning": error_msg},
                    "Balthasar": {"status": "Error", "reasoning": error_msg},
                    "Casper": {"status": "Error", "reasoning": error_msg}
                },
                "synthesis": error_msg
            }

        # 3. Parse the Result
        parsed_responses = self.parse_single_shot_response(full_text)
        
        return {
            "responses": {
                "Melchior": parsed_responses.get("Melchior", {"status": "Error", "reasoning": "Parsing Error"}),
                "Balthasar": parsed_responses.get("Balthasar", {"status": "Error", "reasoning": "Parsing Error"}),
                "Casper": parsed_responses.get("Casper", {"status": "Error", "reasoning": "Parsing Error"})
            },
            "synthesis": parsed_responses.get("Verdict", "Parsing Error")
        }

    def parse_single_shot_response(self, text):
        """
        Extracts sections like [MELCHIOR]...[BALTHASAR]... from the single text.
        Then parses STATUS and REASONING for each sage.
        """
        sections = {}
        
        # Normalize newlines
        text = text.replace("\r\n", "\n")
        
        # Simple Regex to find headers
        patterns = {
            "Melchior": r"\[MELCHIOR\](.*?)(?=\[BALTHASAR\]|\[CASPER\]|\[VERDICT\]|$)",
            "Balthasar": r"\[BALTHASAR\](.*?)(?=\[CASPER\]|\[VERDICT\]|$)",
            "Casper": r"\[CASPER\](.*?)(?=\[VERDICT\]|$)",
            "Verdict": r"\[VERDICT\](.*?)$"
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                raw_content = match.group(1).strip()
                
                # Parse Status and Reasoning for Sages AND Verdict
                status_match = re.search(r"STATUS:\s*(.*?)\n", raw_content)
                reasoning_match = re.search(r"REASONING:\s*(.*)", raw_content, re.DOTALL)
                
                status = status_match.group(1).strip() if status_match else "Unknown"
                reasoning = reasoning_match.group(1).strip() if reasoning_match else raw_content
                
                # Normalize Status for UI colors
                status_upper = status.upper()
                if "承認" in status or "APPROVAL" in status_upper:
                    status = "APPROVAL"
                elif "否決" in status or "DENIAL" in status_upper:
                    status = "DENIAL"
                elif "保留" in status or "RETENTION" in status_upper:
                    status = "RETENTION"
                    
                sections[key] = {
                    "status": status,
                    "reasoning": reasoning
                }
            else:
                sections[key] = {"status": "Error", "reasoning": "(Response missing)"}
                
        return sections
