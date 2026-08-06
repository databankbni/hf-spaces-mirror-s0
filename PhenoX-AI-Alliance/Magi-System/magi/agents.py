import os
# import google.generativeai as genai # Deprecated
from .config import PERSONAS, GOOGLE_API_KEY
import time
import random

class BaseAgent:
    def __init__(self, name):
        self.name = name

    def respond(self, prompt):
        raise NotImplementedError("Subclasses must implement respond method")

class PersonaAgent(BaseAgent):
    """
    An agent that simulates a specific persona using the Gemini model.
    Used when external API keys are not available.
    """
    def __init__(self, start_persona_name):
        super().__init__(start_persona_name)
        self.persona_config = PERSONAS.get(start_persona_name)
        if not self.persona_config:
            raise ValueError(f"Persona {start_persona_name} not found in config")
        
        self.system_prompt = self.persona_config["system_prompt"]
        self.client = None
        
        if GOOGLE_API_KEY:
            try:
                from google import genai
                self.client = genai.Client(api_key=GOOGLE_API_KEY)
            except ImportError:
                print("Warning: google-genai not installed.")

    def respond(self, prompt):
        if not self.client:
             if GOOGLE_API_KEY:
                try:
                    from google import genai
                    self.client = genai.Client(api_key=GOOGLE_API_KEY)
                except:
                    pass
            
             if not self.client:
                return f"[ERROR] GOOGLE_API_KEY is missing or google-genai not installed."
        
        from .config import MODEL_PRIORITY_LIST
        
        # Try generation with fallback
        for model_name in MODEL_PRIORITY_LIST:
            # Retry mechanism for Rate Limits (429)
            for attempt in range(3):
                try:
                    clean_name = model_name.replace("models/", "")
                    
                    # Construct the prompt with persona instructions
                    full_prompt = f"{self.system_prompt}\n\nUser Question: {prompt}\n\nAnswer:"
                    
                    response = self.client.models.generate_content(
                        model=clean_name,
                        contents=full_prompt
                    )
                    return response.text
                except Exception as e:
                    error_str = str(e)
                    # Check for Rate Limit (429) or Quota issues
                    if "429" in error_str or "quota" in error_str.lower() or "RESOURCE_EXHAUSTED" in error_str:
                        wait_time = (2 ** attempt) + random.uniform(0.5, 1.5)
                        print(f"Rate limit hit for {model_name} (Attempt {attempt+1}/3). Retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue # Retry the same model
                    else:
                        # Log error and continue to next model
                        print(f"Model {model_name} error: {e}")
                        break # Break retry loop, try next model
        
        return "Error: All available models failed. Please check your API key and quotas."

class ExternalAgent(BaseAgent):
    """
    Placeholder for future external API integration (Hugging Face, Groq).
    """
    def __init__(self, name, api_key, provider):
        super().__init__(name)
        self.api_key = api_key
        self.provider = provider

    def respond(self, prompt):
        return f"[ExternalAgent {self.name}] Not implemented yet."
