import gradio as gr
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from peft import PeftModel

# Multi-adaptor config

BASE_MODEL_ID = "facebook/nllb-200-distilled-600M"

PEFT_EN_TO_KAM_ID = "KnoxDevelopers/nllb-200-English-to-Kikamba-lang-translation-lora" 
PEFT_KAM_TO_EN_ID = "KnoxDevelopers/nllb-200-Kikamba-to-English-lang-translation-lora" 

print("[*] Loading base tokenizer and base model...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID)
base_model = AutoModelForSeq2SeqLM.from_pretrained(BASE_MODEL_ID)

print("[*] Loading and structuring multi-adapter pipeline...")
# Load base model and initialize it with English_to_Kikamba adapter
model = PeftModel.from_pretrained(base_model, PEFT_EN_TO_KAM_ID, adapter_name="en_to_kam")

# Load Kikamba_to_English adapter onto same base model instance
model.load_adapter(PEFT_KAM_TO_EN_ID, adapter_name="kam_to_en")

device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)
model.eval()

# Logic
MAX_CHARACTER_LIMIT = 700
BANNED_WORDS = ["offensive_placeholder"] 

def programmatic_guardrails(text):
    text_clean = text.strip()
    if not text_clean:
        return False, "⚠️ Please enter a valid sentence to translate."
    if len(text_clean) > MAX_CHARACTER_LIMIT:
        return False, f"⚠️ Input exceeds the safety limit of {MAX_CHARACTER_LIMIT} characters."
    for word in BANNED_WORDS:
        if word in text_clean.lower():
            return False, "🛑 Safety Violation: Input violates our translation safety policy."
    return True, text_clean

# Adaptor translation inference
def translate_interface(source_text, direction):
    is_safe, sanitized_input = programmatic_guardrails(source_text)
    if not is_safe:
        return sanitized_input
        
    try:
        if direction == "English to Kikamba":
            tokenizer.src_lang = "eng_Latn"
            target_lang = "kam_Latn"
            # Activate EN -> KAM adapter weights
            model.set_adapter("en_to_kam") 
        else:  
            tokenizer.src_lang = "kam_Latn"
            target_lang = "eng_Latn"
            # Activate KAM -> EN adapter weights
            model.set_adapter("kam_to_en") 
            
        # Tokenize the input text
        inputs = tokenizer(sanitized_input, return_tensors="pt").to(device)
        target_lang_id = tokenizer.convert_tokens_to_ids(target_lang)
        
        # Run inference using the currently activated adapter
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

# Gradio UI
custom_theme = gr.themes.Soft(
    font=[gr.themes.GoogleFont("Poppins"), "Arial", "sans-serif"]
)

description_html = """
<div style='text-align: center;'>
    <h1>English ⇄ Kikamba Bi-Directional Translator</h1>
    <p>Powered by two fine-tuned Meta NLLB-200-distilled-600M, LoRA Adapters. Suitable for translations under 500 characters.</p>
    <p>Trained by<a href="https://knoxdevelopers.com/" target="_blank">Knox Systems Developers</a></p>
</div>
"""

with gr.Blocks(theme=custom_theme) as demo:
    gr.HTML(description_html)
    
    direction_selector = gr.Radio(
        choices=["English to Kikamba", "Kikamba to English"],
        value="English to Kikamba",
        label="Translation Direction"
    )
    
    with gr.Row():
        with gr.Column():
            input_box = gr.Textbox(
                label="Source Input Text", 
                placeholder="Type your text here...", 
                lines=4
            )
            submit_btn = gr.Button("Translate Text", variant="primary")
            
        with gr.Column():
            output_box = gr.Textbox(
                label="Translated Output", 
                interactive=False, 
                lines=4
            )
            
    submit_btn.click(
        fn=translate_interface, 
        inputs=[input_box, direction_selector], 
        outputs=output_box
    )
    
    gr.Examples(
        examples=[
            ["The children are playing outside near the tree.", "English to Kikamba"],
            ["Where is the market? I need to buy some food.", "English to Kikamba"],
            ["Thank you very much for your kind help today.", "English to Kikamba"],
            ["We are returning home tomorrow morning.", "English to Kikamba"],
            ["Kavyũ kaa nĩ koĩ", "Kikamba to English"],
            ["Thĩna ũsu wĩmbaĩsya too", "Kikamba to English"],
            ["Nzĩa yaĩle kwalala mũthemba ũũ", "Kikamba to English"],
            ["Lĩu ũsu nũkũanda watiwa wĩ mũkunũe", "Kikamba to English"]
        ],
        inputs=[input_box, direction_selector]
    )

demo.launch()