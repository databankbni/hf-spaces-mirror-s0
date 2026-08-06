import os
import re
import torch
import gradio as gr
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

MODEL_ID = os.getenv("MODEL_ID", "MBZUAI/LaMini-Flan-T5-783M")

torch.set_num_threads(int(os.getenv("TORCH_THREADS", "4")))

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForSeq2SeqLM.from_pretrained(
    MODEL_ID,
    dtype=torch.float32,
    low_cpu_mem_usage=True,
)
model.eval()

RULES = """Answer as PayAssured's read-only case assistant.
Use only the supplied PayAssured context.
Do not invent data.
Do not output JSON.
Do not repeat instructions.
If case data exists, summarize it directly.
Keep the answer short and business-friendly.
"""

def clean(text):
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"\b(hf_[A-Za-z0-9_]+|AIza[0-9A-Za-z_-]{20,})\b", "[redacted]", text)
    return text.replace("<pad>", "").replace("</s>", "").strip()

def chat_function(message: str):
    message = (message or "").strip()
    if not message:
        return "Ask me about a case status, payment summary, overdue amount, pending recovery, or a case ID."

    prompt = f"{RULES}\n\nPayAssured context and user request:\n{message}\n\nAnswer:"
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1536)

    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=180,
            num_beams=1,
            do_sample=False,
            repetition_penalty=1.08,
            early_stopping=True,
        )

    return clean(tokenizer.decode(output[0], skip_special_tokens=True)) or "I could not generate a reliable answer."

demo = gr.Interface(
    fn=chat_function,
    inputs=gr.Textbox(label="Message", lines=8),
    outputs=gr.Textbox(label="Response", lines=10),
    title="PayAssured Partner Chat",
    api_name="chat_function",
)

if __name__ == "__main__":
    demo.queue(max_size=8).launch()