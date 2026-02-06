# Makefile for WASDE Platform

VENV = venv
PYTHON = $(VENV)/bin/python3
PIP = $(VENV)/bin/pip3
STREAMLIT = $(VENV)/bin/streamlit

.PHONY: setup
setup:
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt

.PHONY: collect
collect:
	$(PYTHON) src/data_collection.py

.PHONY: parse
parse:
	$(PYTHON) src/wasde_parser.py

.PHONY: analyze
analyze:
	$(PYTHON) src/market_analysis.py
	$(PYTHON) src/economic_calendar_analysis.py

.PHONY: db-init
db-init:
	$(PYTHON) src/database_manager.py

.PHONY: api
api:
	$(PYTHON) api/index.py

.PHONY: dashboard
dashboard dasboard:
	$(STREAMLIT) run src/dashboard.py

.PHONY: terminal
terminal:
	$(PYTHON) src/terminal_dashboard.py

.PHONY: scheduler
scheduler:
	$(PYTHON) src/scheduler.py

.PHONY: aws-setup
aws-setup:
	bash aws_setup.sh

.PHONY: run-all
run-all: db-init parse analyze terminal

.PHONY: clean
clean:
	rm -rf data/wasde/*.txt
	rm -rf data/stocks/*.csv
	rm -rf data/*.db
	find . -type d -name "__pycache__" -exec rm -rf {} +
