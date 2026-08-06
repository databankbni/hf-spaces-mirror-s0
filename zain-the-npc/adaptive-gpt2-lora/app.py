import torch
import gradio as gr
from transformers import GPT2LMHeadModel, GPT2Tokenizer
from lora.gpt2_lora import inject_lora_gpt2

device = "cuda" if torch.cuda.is_available() else "cpu"
tokenizer = GPT2Tokenizer.from_pretrained("gpt2")
tokenizer.pad_token = tokenizer.eos_token

ADAPTERS = {
    "Motivational Coach": "adapters/motivational_coach.pt",
    "Pirate": "adapters/pirate_speak_lines.pt",
    "Shakespearean": "adapters/shakespearean_lines.pt",
    "Sarcastic Gen-Z": "adapters/genz_sarcastic_lines.pt",
    "Noir Detective": "adapters/noir_detective_lines.pt",
}

# Load ONE base model, inject LoRA structure once
model = GPT2LMHeadModel.from_pretrained("gpt2").to(device)
inject_lora_gpt2(model, r=8, alpha=16)
model.to(device)
model.eval()

current_persona = {"name": None}


def load_persona(name):
    if current_persona["name"] == name:
        return
    state = torch.load(ADAPTERS[name], map_location=device, weights_only=True)
    model.load_state_dict(state, strict=False)
    current_persona["name"] = name


def chat(message, persona):
    load_persona(persona)
    inputs = tokenizer(message, return_tensors="pt").to(device)
    out = model.generate(
        **inputs, max_new_tokens=50, do_sample=True,
        top_p=0.9, temperature=0.85, pad_token_id=tokenizer.eos_token_id
    )
    return tokenizer.decode(out[0], skip_special_tokens=True)


with gr.Blocks(title="One Model, Many Minds") as demo:
    gr.Markdown("# 🎭 One Model, Many Minds\nSame GPT-2, swappable LoRA personas — hand-written LoRA, no `peft`.")
    persona = gr.Dropdown(list(ADAPTERS.keys()), value="Motivational Coach", label="Persona")
    msg = gr.Textbox(label="Your message")
    out = gr.Textbox(label="Response")
    btn = gr.Button("Send")
    btn.click(chat, inputs=[msg, persona], outputs=out)

demo.launch()