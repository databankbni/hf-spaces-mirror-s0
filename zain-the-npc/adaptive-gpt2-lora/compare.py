import torch
from transformers import GPT2LMHeadModel, GPT2Tokenizer
from lora.gpt2_lora import inject_lora_gpt2

device = "cuda" if torch.cuda.is_available() else "cpu"
tokenizer = GPT2Tokenizer.from_pretrained("gpt2")
tokenizer.pad_token = tokenizer.eos_token

prompt = "I feel like giving up on my goals."
inputs = tokenizer(prompt, return_tensors="pt").to(device)

# Base model
base_model = GPT2LMHeadModel.from_pretrained("gpt2").to(device)
base_out = base_model.generate(**inputs, max_new_tokens=40, do_sample=True, top_p=0.9, temperature=0.8)
print("BASE:\n", tokenizer.decode(base_out[0], skip_special_tokens=True))
print()

# Fine-tuned model
ft_model = GPT2LMHeadModel.from_pretrained("gpt2").to(device)
inject_lora_gpt2(ft_model, r=8, alpha=16)
ft_model.to(device)
lora_state = torch.load("adapters/motivational_coach.pt", map_location=device)
ft_model.load_state_dict(lora_state, strict=False)

ft_out = ft_model.generate(**inputs, max_new_tokens=40, do_sample=True, top_p=0.9, temperature=0.8)
print("FINE-TUNED (Motivational Coach):\n", tokenizer.decode(ft_out[0], skip_special_tokens=True))
