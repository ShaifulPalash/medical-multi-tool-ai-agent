.PHONY: help install install-dev data build run test test-queries lint fmt

help:
	@echo "make install       - install runtime dependencies"
	@echo "make install-dev   - install runtime + dev dependencies"
	@echo "make data          - download + inspect the 3 Kaggle datasets"
	@echo "make build         - build the 3 SQLite databases from data/"
	@echo "make run           - run the CLI agent (main.py)"
	@echo "make test          - run the automated test suite (no API key needed)"
	@echo "make test-queries  - run 8 live example questions against the real agent (needs API key)"
	@echo "make lint          - run ruff lint checks"
	@echo "make fmt           - auto-fix lint issues with ruff"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

data:
	python scripts/download_and_inspect.py

build:
	python scripts/build_databases.py

run:
	python main.py

test:
	pytest tests/ -v

test-queries:
	python scripts/test_queries.py

lint:
	ruff check .

fmt:
	ruff check . --fix
