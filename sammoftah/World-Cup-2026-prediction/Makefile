.PHONY: prepare test data evaluate run matchday forecast upcoming-forecasts market-evaluate vector-calibration-evaluate track-record qlora-gate bracket-verify health host-evaluate opener-evaluate release-preflight sunday

prepare:
	PYTHONPATH=src python3 scripts/prepare_matches.py

test:
	PYTHONPATH=src:. pytest

data:
	PYTHONPATH=src python3 scripts/generate_synthetic_data.py --split train --count 700 --seed 42 --output data/scenarios/train.jsonl
	PYTHONPATH=src python3 scripts/generate_synthetic_data.py --split validation --count 56 --seed 314 --output data/scenarios/validation.jsonl
	PYTHONPATH=src python3 scripts/generate_synthetic_data.py --split test --count 98 --seed 2718 --output data/scenarios/test.jsonl
	PYTHONPATH=src python3 scripts/audit_dataset.py

evaluate:
	UNDERDOG_EXTRACTOR=mock PYTHONPATH=src python3 scripts/evaluate_extractor.py

run:
	UNDERDOG_EXTRACTOR=mock python3 app.py

matchday:
	@test -n "$(DATE)" || (echo "Usage: make matchday DATE=2026-06-14" && exit 1)
	PYTHONPATH=src python3 scripts/generate_forecast.py --date $(DATE)

forecast:
	PYTHONPATH=src python3 scripts/generate_forecast.py

upcoming-forecasts:
	PYTHONPATH=src python3 scripts/generate_upcoming_forecasts.py

market-evaluate:
	@test -n "$(ODDS)" || (echo "Usage: make market-evaluate ODDS=data/market/odds.csv HORIZON=closing" && exit 1)
	@test -n "$(HORIZON)" || (echo "HORIZON must be opening or closing" && exit 1)
	PYTHONPATH=src python3 scripts/market_blend_evaluation.py --odds $(ODDS) --horizon $(HORIZON)

vector-calibration-evaluate:
	cd scripts && PYTHONPATH=../src:. python3 vector_calibration_evaluation.py

track-record:
	PYTHONPATH=src python3 scripts/track_record_summary.py

qlora-gate:
	PYTHONPATH=src python3 scripts/close_qlora_gate.py

bracket-verify:
	PYTHONPATH=src python3 scripts/verify_world_cup_bracket.py

health:
	PYTHONPATH=src python3 scripts/health_check.py

host-evaluate:
	cd scripts && PYTHONPATH=../src:. python3 host_adjustment_evaluation.py

opener-evaluate:
	cd scripts && PYTHONPATH=../src:. python3 opener_draw_evaluation.py

release-preflight: qlora-gate bracket-verify
	PYTHONPATH=src python3 scripts/submission_preflight.py --online

sunday: test qlora-gate bracket-verify health
	PYTHONPATH=src python3 scripts/audit_dataset.py
	PYTHONPATH=src python3 scripts/submission_preflight.py --allow-human-pending
