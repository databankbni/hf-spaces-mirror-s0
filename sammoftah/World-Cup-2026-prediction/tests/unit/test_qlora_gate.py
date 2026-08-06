from underdog_lab.release.qlora_gate import evaluate_qlora_gate


def _metrics(f1, attribution, fallback, schema=1.0, latency=1000):
    return {
        "factor_micro_f1": f1,
        "team_attribution_accuracy": attribution,
        "fallback_rate": fallback,
        "schema_validity_rate": schema,
        "median_latency_ms": latency,
    }


def test_gate_closes_a_consistent_no_ship_decision():
    report = evaluate_qlora_gate(
        _metrics(0.03, 0.05, 0.09),
        _metrics(0.04, 0.03, 0.17),
        {"ship_decision": "NO-SHIP"},
    )

    assert report["status"] == "closed"
    assert report["computed_decision"] == "NO-SHIP"
    assert report["release_blocking"] is False
    assert "minimum_f1_gain" in report["failed_checks"]
    assert "no_attribution_regression" in report["failed_checks"]


def test_gate_rejects_a_declared_ship_that_misses_thresholds():
    report = evaluate_qlora_gate(
        _metrics(0.03, 0.05, 0.09),
        _metrics(0.04, 0.03, 0.17),
        {"ship_decision": "SHIP"},
    )

    assert report["status"] == "invalid"
    assert report["release_blocking"] is True


def test_gate_allows_a_material_non_regressing_improvement():
    report = evaluate_qlora_gate(
        _metrics(0.20, 0.50, 0.10),
        _metrics(0.36, 0.52, 0.11),
        {"ship_decision": "SHIP"},
    )

    assert report["status"] == "closed"
    assert report["computed_decision"] == "SHIP"
    assert all(report["checks"].values())
