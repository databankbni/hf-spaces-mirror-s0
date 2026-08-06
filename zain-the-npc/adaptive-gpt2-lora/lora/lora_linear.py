"""
Hand-written LoRA implementation. No peft library.
Wraps a frozen nn.Linear layer and adds trainable low-rank adapters A, B.

Math:
    y = Wx + (alpha/r) * B(Ax)

W  : frozen base weight (untouched)
A  : (r, in_features)  - down-projection, random init
B  : (out_features, r) - up-projection, zero init (adapter starts as no-op)
"""

import torch
import torch.nn as nn
import math


class LoRALinear(nn.Module):
    def __init__(self, base_linear: nn.Linear, r: int = 8, alpha: int = 16, dropout: float = 0.0):
        super().__init__()
        self.base = base_linear
        self.in_features = base_linear.in_features
        self.out_features = base_linear.out_features
        self.r = r
        self.alpha = alpha
        self.scaling = alpha / r

        # Freeze the base layer completely
        self.base.weight.requires_grad = False
        if self.base.bias is not None:
            self.base.bias.requires_grad = False

        # A: down-projection (r, in_features) - random init, small std
        self.A = nn.Parameter(torch.randn(r, self.in_features) * (1 / math.sqrt(r)))
        # B: up-projection (out_features, r) - zero init so adapter starts as identity/no-op
        self.B = nn.Parameter(torch.zeros(self.out_features, r))

        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    def forward(self, x):
        # y1: frozen base path
        y1 = self.base(x)

        # y2: adapter path -> Ax then B(Ax), scaled
        x_dropped = self.dropout(x)
        ax = x_dropped @ self.A.T          # (batch, seq, r)
        y2 = ax @ self.B.T                 # (batch, seq, out_features)
        y2 = y2 * self.scaling

        return y1 + y2

    def merge(self):
        """Optional: fold A,B into W permanently for clean single-matrix inference."""
        with torch.no_grad():
            delta_w = (self.B @ self.A) * self.scaling
            self.base.weight += delta_w
        return self.base  # now a plain nn.Linear again, no adapter overhead

    def trainable_params(self):
        return [self.A, self.B]


def inject_lora(model, target_modules=("c_attn",), r=8, alpha=16, dropout=0.0):
    """
    Walk the model, replace target Linear/Conv1D layers with LoRALinear wrappers.
    For GPT-2 specifically, attention uses Conv1D not Linear - handled separately
    in gpt2_lora.py since GPT-2's HF implementation uses a transposed weight convention.
    """
    replaced = []
    for name, module in model.named_modules():
        for child_name, child in module.named_children():
            if any(t in child_name for t in target_modules) and isinstance(child, nn.Linear):
                lora_layer = LoRALinear(child, r=r, alpha=alpha, dropout=dropout)
                setattr(module, child_name, lora_layer)
                replaced.append(f"{name}.{child_name}")
    return replaced


def count_trainable_params(model):
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    return trainable, total, 100 * trainable / total
