"""
GPT-2 (HuggingFace) stores attention weights as Conv1D, not nn.Linear.
Conv1D weight shape: (in_features, out_features) - opposite of nn.Linear's (out, in).
This wrapper handles that so LoRA math still applies correctly.
"""

import torch
import torch.nn as nn
import math
from transformers.pytorch_utils import Conv1D


class LoRAConv1D(nn.Module):
    def __init__(self, base_conv1d: Conv1D, r: int = 8, alpha: int = 16, dropout: float = 0.0):
        super().__init__()
        self.base = base_conv1d
        # Conv1D weight: (in_features, out_features)
        self.in_features, self.out_features = self.base.weight.shape
        self.r = r
        self.alpha = alpha
        self.scaling = alpha / r

        self.base.weight.requires_grad = False
        self.base.bias.requires_grad = False

        self.A = nn.Parameter(torch.randn(r, self.in_features) * (1 / math.sqrt(r)))
        self.B = nn.Parameter(torch.zeros(self.out_features, r))
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    def forward(self, x):
        y1 = self.base(x)  # frozen path, Conv1D handles its own math

        x_dropped = self.dropout(x)
        ax = x_dropped @ self.A.T   # (..., r)
        y2 = ax @ self.B.T          # (..., out_features)
        y2 = y2 * self.scaling

        return y1 + y2

    def trainable_params(self):
        return [self.A, self.B]


def inject_lora_gpt2(model, target_modules=("c_attn",), r=8, alpha=16, dropout=0.0):
    """Replace GPT-2's c_attn (qkv combined) Conv1D layers with LoRAConv1D wrappers."""
    replaced = []
    for block in model.transformer.h:
        for name in target_modules:
            if hasattr(block.attn, name):
                orig = getattr(block.attn, name)
                if isinstance(orig, Conv1D):
                    setattr(block.attn, name, LoRAConv1D(orig, r=r, alpha=alpha, dropout=dropout))
                    replaced.append(name)
    return replaced


def freeze_base_unfreeze_lora(model):
    """Make sure ONLY A,B params are trainable, everything else frozen."""
    for name, param in model.named_parameters():
        param.requires_grad = ("A" in name.split(".") or "B" in name.split("."))
    return model


def get_lora_trainable_params(model):
    return [p for n, p in model.named_parameters() if p.requires_grad]
