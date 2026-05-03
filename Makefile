.PHONY: install test test-unit lint format type-check run docker-build docker-run pre-commit clean help

PYTHON := python
PYTEST := python -m pytest
RUFF := ruff
MYPY := mypy

help:
	@echo "Available targets:"
	@echo "  install        Install all dependencies via uv"
	@echo "  test           Run all tests"
	@echo "  test-unit      Run only unit tests"
	@echo "  lint           Run ruff check"
	@echo "  format         Run ruff format"
	@echo "  type-check     Run mypy"
	@echo "  pre-commit     Run pre-commit hooks on all files"
	@echo "  run            Run the test harness (main.py)"
	@echo "  docker-build   Build the Docker image"
	@echo "  docker-run     Run the Docker container"
	@echo "  clean          Remove build artifacts and caches"

install:
	uv sync --all-extras

test:
	$(PYTEST) tests/ -v

test-unit:
	$(PYTEST) tests/unit/ -v

lint:
	$(RUFF) check src/ tests/

format:
	$(RUFF) format src/ tests/

type-check:
	$(MYPY) src/

pre-commit:
	pre-commit run --all-files

run:
	$(PYTHON) src/app/main.py

docker-build:
	docker build -t invoice-agent:latest .

docker-run:
	docker run --rm \
		--env-file .env \
		invoice-agent:latest

clean:
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
