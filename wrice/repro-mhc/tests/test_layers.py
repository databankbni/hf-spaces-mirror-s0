import torch
import pytest
from mhc_repro.layers import (
    StandardResidualLayer,
    HyperConnectionLayer,
    ManifoldHyperConnectionLayer,
)

def test_layer_tensor_shapes():
    B, K, d = 4, 3, 16
    x = torch.randn(B, K, d)

    # Standard residual (operates on single stream or batched stream)
    std_layer = StandardResidualLayer(d)
    x_single = torch.randn(B, d)
    y_single = std_layer(x_single)
    assert y_single.shape == (B, d)

    # Unconstrained Hyper-Connection
    hc_layer = HyperConnectionLayer(K=K, d_model=d)
    y_hc = hc_layer(x)
    assert y_hc.shape == (B, K, d)

    # Manifold-Constrained Hyper-Connection (mHC)
    mhc_layer = ManifoldHyperConnectionLayer(K=K, d_model=d)
    y_mhc = mhc_layer(x)
    assert y_mhc.shape == (B, K, d)

def test_mhc_residual_matrix_is_doubly_stochastic():
    K, d = 4, 16
    mhc_layer = ManifoldHyperConnectionLayer(K=K, d_model=d)
    H_res = mhc_layer.get_effective_residual_matrix()

    # Check row & column sums = 1
    assert torch.allclose(torch.sum(H_res, dim=-1), torch.ones(K), atol=1e-4)
    assert torch.allclose(torch.sum(H_res, dim=-2), torch.ones(K), atol=1e-4)
    assert torch.all(H_res >= 0)
