PYTHON = /opt/anaconda3/bin/python3

.PHONY: setup build serve ui run clean

setup:
	pip install -r requirements.txt

ingest:
	PYTHONPATH=. $(PYTHON) src/data/ingest_papers.py

build: ingest

serve:
	PYTHONPATH=. uvicorn src.serving.app:app --host 0.0.0.0 --port 8002 --reload

ui:
	PYTHONPATH=. $(PYTHON) app.py

run:
	PYTHONPATH=. $(PYTHON) -c "\
from src.agent.design_agent import DesignAgent; \
a = DesignAgent(); \
r = a.run('Design a lightweight suspension bracket for a BEV. Max weight 1.5kg, min yield strength 350MPa, 100k units/year. Priority: weight.'); \
print(r['evaluation']['recommended'])"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true

mlflow:
	mlflow ui --port 5001
