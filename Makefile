.PHONY: install run test cov lint bench docker
install:
	pip install -r requirements-dev.txt && pip install -e .
run:
	uvicorn mfasha.api.main:create_app --factory --reload --port 8000
test:
	pytest -m "not performance"
cov:
	pytest --cov=mfasha --cov-report=term-missing -m "not performance"
perf:
	pytest -m performance -s
lint:
	ruff check src tests scripts
bench:
	python scripts/benchmark.py
docker:
	docker compose up --build
