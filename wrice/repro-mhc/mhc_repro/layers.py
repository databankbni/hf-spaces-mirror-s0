"""Implementation of Residual, Hyper-Connection (HC), and Manifold Hyper-Connection (mHC) layers."""

import torch
import torch.nn as nn
import torch.nn.functional as F
from .sinkhorn import sinkhorn_knopp_projection

class StandardResidualLayer(nn.Module):
    """Standard residual layer: y = x + F(x)."""

    def __init__(self, d_model: int):
        super().__init__()
        self.fc1 = nn.Linear(d_model, d_model * 2)
        self.fc2 = nn.Linear(d_model * 2, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # F(x) = GELU(x W1) W2
        residual = self.fc2(F.gelu(self.fc1(x)))
        return x + residual

class HyperConnectionLayer(nn.Module):
    """Unconstrained Hyper-Connection (HC) layer across K streams."""

    def __init__(self, K: int, d_model: int):
        super().__init__()
        self.K = K
        self.d_model = d_model

        # Unconstrained learnable mapping weights
        self.W_pre = nn.Parameter(torch.randn(K))
        self.W_post = nn.Parameter(torch.randn(K))
        self.W_res = nn.Parameter(torch.randn(K, K))

        self.fc1 = nn.Linear(d_model, d_model * 2)
        self.fc2 = nn.Linear(d_model * 2, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (B, K, d_model)
        # 1. H_pre mapping: combine K streams into single layer input
        # u = sum_k (W_pre[k] * x[:, k, :]) -> (B, d_model)
        u = torch.einsum("k, bkd -> bd", self.W_pre, x)

        # 2. Layer transform F(u)
        v = self.fc2(F.gelu(self.fc1(u)))  # (B, d_model)

        # 3. H_post mapping: map v to K streams
        y_post = torch.einsum("k, bd -> bkd", self.W_post, v)  # (B, K, d_model)

        # 4. H_res mapping: unconstrained matrix multiplication across K streams
        x_res = torch.einsum("ij, bjd -> bid", self.W_res, x)  # (B, K, d_model)

        return x_res + y_post

class ManifoldHyperConnectionLayer(nn.Module):
    """Manifold-Constrained Hyper-Connection (mHC) layer."""

    def __init__(
        self,
        K: int,
        d_model: int,
        n_sinkhorn_iters: int = 20,
        pre_mode: str = "manifold",
        post_mode: str = "manifold",
        res_mode: str = "manifold",
    ):
        super().__init__()
        self.K = K
        self.d_model = d_model
        self.n_sinkhorn_iters = n_sinkhorn_iters
        self.pre_mode = pre_mode
        self.post_mode = post_mode
        self.res_mode = res_mode

        # Parameter logits
        self.W_pre = nn.Parameter(torch.randn(K))
        self.W_post = nn.Parameter(torch.randn(K))
        self.W_res = nn.Parameter(torch.randn(K, K))

        self.fc1 = nn.Linear(d_model, d_model * 2)
        self.fc2 = nn.Linear(d_model * 2, d_model)

    def get_effective_pre(self) -> torch.Tensor:
        if self.pre_mode == "fixed":
            return torch.full((self.K,), 1.0 / self.K, device=self.W_pre.device)
        elif self.pre_mode == "unconstrained":
            return self.W_pre
        else:  # manifold
            return F.softmax(self.W_pre, dim=-1)

    def get_effective_post(self) -> torch.Tensor:
        if self.post_mode == "fixed":
            return torch.full((self.K,), 1.0 / self.K, device=self.W_post.device)
        elif self.post_mode == "unconstrained":
            return self.W_post
        else:  # manifold
            return F.softmax(self.W_post, dim=-1)

    def get_effective_residual_matrix(self) -> torch.Tensor:
        if self.res_mode == "fixed":
            return torch.eye(self.K, device=self.W_res.device)
        elif self.res_mode == "unconstrained":
            return self.W_res
        else:  # manifold (Sinkhorn-Knopp projection)
            return sinkhorn_knopp_projection(self.W_res, n_iters=self.n_sinkhorn_iters)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (B, K, d_model)
        H_pre = self.get_effective_pre()
        H_post = self.get_effective_post()
        H_res = self.get_effective_residual_matrix()

        # 1. H_pre mapping
        u = torch.einsum("k, bkd -> bd", H_pre, x)

        # 2. Layer transform F(u)
        v = self.fc2(F.gelu(self.fc1(u)))

        # 3. H_post mapping
        y_post = torch.einsum("k, bd -> bkd", H_post, v)

        # 4. H_res mapping (manifold-constrained)
        x_res = torch.einsum("ij, bjd -> bid", H_res, x)

        return x_res + y_post
