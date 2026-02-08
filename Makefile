SHELL := /bin/bash
.RECIPEPREFIX := >
PY := venv/bin/python
PIP := $(PY) -m pip

.PHONY: help pip install install-dev test lint format ci run smoke doctor

help:
>echo "Targets:"
>echo "  make pip         - upgrade pip/setuptools/wheel (safe)"
>echo "  make install     - install runtime deps"
>echo "  make install-dev - install dev deps"
>echo "  make test        - run pytest"
>echo "  make lint        - run ruff check (only project code)"
>echo "  make format      - run ruff format (only project code)"
>echo "  make ci          - lint + test"
>echo "  make run         - run bot module (like systemd)"
>echo "  make smoke       - run coworkingbot-doctor --smoke"
>echo "  make doctor      - print coworkingbot-doctor usage"

pip:
>$(PIP) install -U pip setuptools wheel

install:
>$(PIP) install -r requirements.txt

install-dev:
>$(PIP) install -r requirements-dev.txt

test:
>$(PY) -m pytest -q

lint:
>$(PY) -m ruff check coworkingbot tests

format:
>$(PY) -m ruff format coworkingbot tests

ci: lint test

run:
>$(PY) -m coworkingbot.working_bot_fixed

smoke:
>./coworkingbot-doctor.sh --smoke

doctor:
>@echo "Usage: ./coworkingbot-doctor.sh --smoke"
