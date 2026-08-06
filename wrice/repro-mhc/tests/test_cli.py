import json

from mhc_repro.cli import build_evidence, write_evidence


EXPECTED_BINDINGS = {
    "claim-1": "bdf296450b900b06ca2efbc1ffe702d9547371e3d847e6a31c71d977e0bfa052",
    "claim-2": "fa35812d9e1626bcfe1702f946f3926128f6012071af6ef378e0241e30881823",
    "claim-3": "15537486e4923b51864ce7b52999581519cde779ca9e03eda2ad93117abc9735",
    "claim-4": "2fd1e3570d1437de16597b0b942dc8d2f4a0045e84fd066bf01da44a86c86959",
    "claim-5": "f67e1f1f781f58d9e6c928002254a5dda7d94078db32408893971d6985094a02",
}


def test_evidence_binds_all_live_claims_with_honest_statuses():
    bundle = build_evidence()
    claims = {claim["claim_id"]: claim for claim in bundle["claims"]}

    assert bundle["attempt_id"] == "3d164e18-39ef-416e-b986-96b5a5d4e12d"
    assert {claim_id: claim["status"] for claim_id, claim in claims.items()} == {
        "claim-1": "partial",
        "claim-2": "partial",
        "claim-3": "partial",
        "claim-4": "unavailable",
        "claim-5": "unavailable",
    }
    assert {
        claim_id: claim["challenge_claim_sha256"]
        for claim_id, claim in claims.items()
    } == EXPECTED_BINDINGS
    assert claims["claim-2"]["evidence_kind"] == "toy_dimensional_ablation"
    assert claims["claim-3"]["evidence_kind"] == "toy_random_matrix_propagation"
    assert "27B" in claims["claim-5"]["limitation"]
    assert len(bundle["dimensional_ablations"]) == 216
    assert len(bundle["toy_propagation"]) == 27
    assert bundle["summary"]["all_claims_verified"] is False
    assert bundle["provenance"]["api_cost_usd"] == 0.0
    assert bundle["provenance"]["device"] == "cpu"


def test_serialized_evidence_is_strict_and_byte_reproducible(tmp_path):
    bundle = build_evidence()
    first_json = tmp_path / "first.json"
    first_csv = tmp_path / "first.csv"
    second_json = tmp_path / "second.json"
    second_csv = tmp_path / "second.csv"

    write_evidence(bundle, first_json, first_csv)
    write_evidence(build_evidence(), second_json, second_csv)

    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_csv.read_bytes() == second_csv.read_bytes()
    json.loads(
        first_json.read_text(),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
