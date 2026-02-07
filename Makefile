SHELL := /bin/bash
PY := venv/bin/python
PIP := $(PY) -m pip

.PHONY: help pip install install-dev test lint format ci run

help:
	@echo "Targets:"
	@echo "  make pip         - upgrade pip/setuptools/wheel (safe)"
	@echo "  make install     - install runtime deps"
	@echo "  make install-dev - install dev deps"
	@echo "  make test        - run pytest"
	@echo "  make lint        - run ruff check"
	@echo "  make format      - run ruff format"
	@echo "  make ci          - lint + test"
	@echo "  make run         - run bot module (like systemd)"

pip:
	$(PIP) install -U pip setuptools wheel

install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements-dev.txt

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check .

format:
	$(PY) -m ruff format .

ci: lint test

run:
	$(PY) -m coworkingbot.working_bot_fixed
