VENV    := .venv
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
PYTEST  := $(VENV)/bin/pytest
CELERY  := $(VENV)/bin/celery

ENV_FILE := src/config/env

.PHONY: setup-lite setup-full env env-lite update run worker test help

##
## Installation modes:
##
##   setup-lite  — SQLite, sequential processing. No OS services required.
##                 Simpler setup, slower import. Best for personal use.
##
##   setup-full  — PostgreSQL + Celery. Run ./setup.sh first to install OS
##                 dependencies (PostgreSQL, RabbitMQ). Parallel processing.
##                 Best for development and large collections.
##

## setup-lite  — install lite stack (SQLite, no broker/worker required)
setup-lite: $(VENV)/.deps-installed env-lite
	@echo "[setup] Running database migrations..."
	@$(PYTHON) manage.py migrate
	@echo ""
	@echo "Done. Run 'make run' to start the server."

## setup-full  — install full stack (PostgreSQL + Celery); run ./setup.sh first for OS deps
setup-full: $(VENV)/.deps-installed env
	@echo "[setup] Running database migrations..."
	@$(PYTHON) manage.py migrate
	@echo ""
	@echo "Done. Run 'make run' to start the server and 'make worker' to start the Celery worker."

## env         — generate src/config/env from settings defaults (skips if already exists)
env:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "[env] Generating $(ENV_FILE) from settings defaults..."; \
		python3 -c "$$GENERATE_ENV"; \
		echo "[env] $(ENV_FILE) written — edit it to customise your installation"; \
	else \
		echo "[skip] $(ENV_FILE) already exists"; \
	fi

## env-lite    — write src/config/env configured for SQLite, sequential processing
env-lite:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "[env] Writing SQLite/lite env to $(ENV_FILE)..."; \
		printf 'DB_ENGINE=django.db.backends.sqlite3\nDB_NAME=db.sqlite3\nUSE_ASYNC_TASKS=False\n' > $(ENV_FILE); \
		echo "[env] $(ENV_FILE) written — edit it to customise your installation"; \
	else \
		echo "[skip] $(ENV_FILE) already exists"; \
	fi

define GENERATE_ENV
import re
content = open("src/config/settings.py").read()
pattern = r'env\.\w+\(\s*"(\w+)"\s*,\s*default=([^)]+)\)'
lines = []
for name, raw in re.findall(pattern, content):
    val = raw.strip().strip('"')
    lines.append(name + "=" + val)
open("src/config/env", "w").write("\n".join(lines) + "\n")
endef
export GENERATE_ENV

# Re-run pip only when requirements.txt changes (sentinel file tracks this).
$(VENV)/.deps-installed: requirements.txt $(VENV)/bin/activate
	@echo "[setup] Installing Python dependencies..."
	@$(PIP) install --quiet -r requirements.txt
	@touch $@

$(VENV)/bin/activate:
	@echo "[setup] Creating virtual environment..."
	@python3 -m venv $(VENV) || { \
		echo ""; \
		echo "Failed to create a virtual environment."; \
		echo "Run ./setup.sh (or ./setup.sh lite) to install all prerequisites,"; \
		echo "or install the missing package manually and retry:"; \
		echo "  sudo apt install python3-venv"; \
		echo ""; \
		exit 1; \
	}

## update      — pull latest changes, install new dependencies, and run migrations
update:
	@echo "[update] Pulling latest changes..."
	@git pull origin main
	@echo "[update] Installing dependencies..."
	@$(PIP) install --quiet -r requirements.txt
	@touch $(VENV)/.deps-installed
	@echo "[update] Running database migrations..."
	@$(PYTHON) manage.py migrate
	@echo ""
	@echo "Done. Run 'make run' to start the server."

## run         — start the Django development server
run:
	@git fetch origin main --quiet 2>/dev/null; \
	BEHIND=$$(git rev-list --count main..origin/main 2>/dev/null); \
	if [ "$$BEHIND" -gt 0 ] 2>/dev/null; then \
		printf '\n\033[1;33m[update] %s new commit(s) available. Run '"'"'make update'"'"' to get the latest changes.\033[0m\n\n' "$$BEHIND"; \
	else \
		printf '\n\033[1;32mYou are on the latest version.\033[0m\n\n'; \
	fi
	@$(PYTHON) manage.py runserver

## worker      — start a Celery worker (full stack only; requires RabbitMQ)
worker:
	$(CELERY) -A src.config worker --loglevel=info --concurrency=8

## test        — run the test suite
test:
	$(PYTEST)

## help        — list available targets
help:
	@grep -E '^## ' Makefile | sed 's/^## //'
