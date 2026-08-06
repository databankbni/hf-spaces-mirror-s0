import gradio as gr
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from peft import PeftModel

# MODEL CONFIGURATION
BASE_MODEL_ID = "facebook/nllb-200-distilled-600M"
PEFT_MODEL_ID = "KnoxDevelopers/nllb-200-English-to-Kikamba-lang-translation-lora" 
TARGET_LANG = "kam_Latn" 

print("[*] Loading base tokenizer and model...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, src_lang="eng_Latn", tgt_lang=TARGET_LANG)
base_model = AutoModelForSeq2SeqLM.from_pretrained(BASE_MODEL_ID)

print("[*] Loading and merging your custom LoRA adapters...")
# Wrap base NLLB model with our adapters
model = PeftModel.from_pretrained(base_model, PEFT_MODEL_ID)

device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)
model.eval()

# GUARDRAIL & SYSTEM PROMPT LOGIC

MAX_CHARACTER_LIMIT = 700
BANNED_WORDS = ["offensive_placeholder"]
#BANNED_WORDS = ["scam", "hack", "exploit"]

def programmatic_guardrails(text):
    """
    Acts as the system prompt layer (our Seq2Seq/Encoder-Decoder
    translation model(NLLB) is not an autoregressive Chat LLM).
    Evaluates inputs against safety guardrails
    before allowing the model to spend compute resources translating them.
    """
    text_clean = text.strip()
    
    # Empty inputs
    if not text_clean:
        return False, "⚠️ Please enter a valid sentence to translate."
        
    # Input length limitation
    if len(text_clean) > MAX_CHARACTER_LIMIT:
        return False, f"⚠️ Input exceeds the safety limit of {MAX_CHARACTER_LIMIT} characters. Please shorten your text."
        
    # Content Filtering / Banned Words
    for word in BANNED_WORDS:
        if word in text_clean.lower():
            return False, "🛑 Safety Violation: Your input contains text that violates our translation safety policy."
            
    return True, text_clean


# TRANSLATION CORE
def translate_interface(english_text):
    # Pass input through our system guardrails first
    is_safe, sanitized_input = programmatic_guardrails(english_text)
    if not is_safe:
        return sanitized_input # Returns the guardrail warning message directly to the UI
        
    # Proceed to translate if safe
    try:
        inputs = tokenizer(sanitized_input, return_tensors="pt").to(device)
        target_lang_id = tokenizer.convert_tokens_to_ids(TARGET_LANG)
        
        with torch.no_grad():
            generated_tokens = model.generate(
                **inputs,
                forced_bos_token_id=target_lang_id,
                max_length=256,
                num_beams=4,
                early_stopping=True
            )
            
        return tokenizer.decode(generated_tokens[0], skip_special_tokens=True)
    except Exception as e:
        return f"An internal error occurred during generation: {str(e)}"


# UI

custom_theme = gr.themes.Origin(
    font=[
        gr.themes.GoogleFont("Poppins"), 
        "Arial",                         
        "sans-serif"                     
    ]
)

description_html = """
<div style='text-align: center;'>
    <h1>English to Kikamba Translator</h1>
    <p>Powered by a fine-tuned Meta NLLB-200-distilled-600M, LoRA Adapter. Suitable for translations under 500 characters.</p>
    <p>Trained by<a href="https://knoxdevelopers.com/" target="_blank">Knox Systems Developers</a></p>
</div>
"""

with gr.Blocks(theme=custom_theme) as demo:
    gr.HTML(description_html)
    
    with gr.Row():
        with gr.Column():
            input_box = gr.Textbox(
                label="English Input", 
                placeholder="Type your English sentence here...", 
                lines=6
            )
            submit_btn = gr.Button("Translate", variant="primary")
            
        with gr.Column():
            output_box = gr.Textbox(
                label="Kikamba Output", 
                interactive=False, 
                lines=6
            )
            
    # Connect UI trigger
    submit_btn.click(
        fn=translate_interface, 
        inputs=input_box, 
        outputs=output_box
    )
    
    gr.Examples(
        examples=[
            ["The children are playing outside near the tree."],
            ["Where is the market? I need to buy some food."],
            ["Thank you very much for your kind help today."],
            ["We are returning home tomorrow morning."]
        ],
        inputs=input_box
    )

demo.launch()