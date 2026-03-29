VENV    := .venv
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
PYTEST  := $(VENV)/bin/pytest
CELERY  := $(VENV)/bin/celery

SETTINGS_SRC    := src/config/settings.py.sample
SETTINGS_TARGET := src/config/settings.py

.PHONY: setup run worker test help

## setup   — create venv, install deps, configure settings, run migrations
setup: $(VENV)/.deps-installed
	@if [ ! -f $(SETTINGS_TARGET) ]; then \
		echo "[setup] Copying settings from sample..."; \
		cp $(SETTINGS_SRC) $(SETTINGS_TARGET); \
		python3 -c "\
import sys; f='$(SETTINGS_TARGET)'; \
c=open(f).read(); \
c=c.replace('your_db_name','fujifilm_recipes') \
  .replace('your_db_user','fujifilm_recipes') \
  .replace('your_db_password','fujifilm_recipes'); \
open(f,'w').write(c)"; \
		echo "[setup] Settings written to $(SETTINGS_TARGET)"; \
	else \
		echo "[skip]  $(SETTINGS_TARGET) already exists"; \
	fi
	@echo "[setup] Running database migrations..."
	@$(PYTHON) manage.py migrate
	@echo ""
	@echo "Done. Run 'make run' to start the server."

# Re-run pip only when requirements.txt changes (sentinel file tracks this).
$(VENV)/.deps-installed: requirements.txt $(VENV)/bin/activate
	@echo "[setup] Installing Python dependencies..."
	@$(PIP) install --quiet -r requirements.txt
	@touch $@

$(VENV)/bin/activate:
	@echo "[setup] Creating virtual environment..."
	@python3 -m venv $(VENV)

## run     — start the Django development server
run:
	$(PYTHON) manage.py runserver

## worker  — start a Celery worker (requires RabbitMQ)
worker:
	$(CELERY) -A src.config worker --loglevel=info --concurrency=8

## test    — run the test suite
test:
	$(PYTEST)

## help    — list available targets
help:
	@grep -E '^## ' Makefile | sed 's/^## //'
