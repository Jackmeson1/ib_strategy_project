# Makefile for Dynamic Leverage Bot

.PHONY: help install install-dev test lint format clean run run-dry env-template

# Default target
help:
	@echo "Available commands:"
	@echo "  make install      - Install production dependencies"
	@echo "  make install-dev  - Install development dependencies"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linting checks"
	@echo "  make format       - Format code"
	@echo "  make clean        - Clean up generated files"
	@echo "  make run          - Run the bot (live mode)"
	@echo "  make run-dry      - Run the bot in dry-run mode"
	@echo "  make env-template - Create .env file from template"

# Install production dependencies
install:
	pip install -r requirements.txt

# Install development dependencies
install-dev:
	pip install -r requirements-dev.txt
	pre-commit install

# Run tests
test:
	pytest tests/ -v

# Run tests with coverage
test-cov:
	pytest --cov=src --cov-report=html --cov-report=term tests/

# Run linting
lint:
	ruff check src/ tests/
	mypy src/ --strict

# Format code
format:
	black src/ tests/ main.py
	isort src/ tests/ main.py

# Clean up
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf htmlcov
	rm -rf .coverage

# Run the bot
run:
	python main.py

# Run in dry-run mode
run-dry:
	python main.py --dry-run

# Run with debug logging
run-debug:
	python main.py --debug

# Create environment file from template
env-template:
	@if [ ! -f .env ]; then \
		python -c "from src.config.settings import ENV_TEMPLATE; print(ENV_TEMPLATE)" > .env.example; \
		cp .env.example .env; \
		echo "Created .env file. Please edit it with your configuration."; \
	else \
		echo ".env file already exists."; \
	fi

# Run pre-commit hooks
pre-commit:
	pre-commit run --all-files

# Docker commands (if using Docker)
ENV_FILE ?= .env

docker-build:
	docker build -t dynamic-leverage-bot .

docker-run:
	docker run --rm -it --env-file $(ENV_FILE) dynamic-leverage-bot

# Development server with auto-reload (useful for testing)
dev:
	python main.py --debug --dry-run
