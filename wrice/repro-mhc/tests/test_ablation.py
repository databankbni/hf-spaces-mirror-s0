from mhc_repro.ablation import run_dimensional_ablations


def test_dimensional_ablations_cover_complete_grid_deterministically():
    kwargs = {
        "stream_counts": (2, 4),
        "hidden_dims": (8, 16),
        "seeds": (17, 42),
        "n_samples": 3,
        "n_sinkhorn_iters": 100,
    }
    first = run_dimensional_ablations(**kwargs)
    second = run_dimensional_ablations(**kwargs)

    assert first == second
    assert len(first) == 2 * 2 * 2 * 8
    assert all(row["output_shape_valid"] for row in first)
    assert {
        (row["stream_count"], row["hidden_dim"], row["seed"])
        for row in first
    } == {
        (stream_count, hidden_dim, seed)
        for stream_count in (2, 4)
        for hidden_dim in (8, 16)
        for seed in (17, 42)
    }
