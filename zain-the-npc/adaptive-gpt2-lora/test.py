from lora.gpt2_lora import inject_lora_gpt2, freeze_base_unfreeze_lora, get_lora_trainable_params
from transformers import GPT2LMHeadModel

model = GPT2LMHeadModel.from_pretrained("gpt2")
inject_lora_gpt2(model, r=8, alpha=16)
freeze_base_unfreeze_lora(model)
print(len(get_lora_trainable_params(model)), "trainable tensors")