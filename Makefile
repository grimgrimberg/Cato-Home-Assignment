SHELL := /bin/bash

PYTHON ?= $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null)
DATE ?= 2026-02-08
TOP ?= 20
REGION ?= us
WATCHLIST ?= watchlist.yaml
OUT ?= runs/$(DATE)
WATCH_OUT ?= runs/watchlist-demo
EMAIL_OUT ?= runs/email-demo

.PHONY: help check-python install install-user venv install-venv test test-models test-golden test-ralph run-movers run-watchlist run-email smoke clean-runs

help:
	@echo "Daily Movers Assistant - Make Targets"
	@echo "  make install         # Install deps with pip"
	@echo "  make install-user    # Install deps with --user --break-system-packages"
	@echo "  make venv            # Create .venv"
	@echo "  make install-venv    # Install deps into .venv"
	@echo "  make test            # Run full pytest"
	@echo "  make run-movers      # Run movers pipeline"
	@echo "  make run-watchlist   # Run watchlist pipeline"
	@echo "  make run-email       # Run movers with --send-email"
	@echo "  make smoke           # test + movers + watchlist"
	@echo ""
	@echo "Variables you can override:"
	@echo "  DATE=$(DATE) TOP=$(TOP) REGION=$(REGION) WATCHLIST=$(WATCHLIST)"
	@echo "  OUT=$(OUT) WATCH_OUT=$(WATCH_OUT) EMAIL_OUT=$(EMAIL_OUT)"

check-python:
	@test -n "$(PYTHON)" || (echo "No python interpreter found (python3/python)." && exit 1)

install: check-python
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

install-user: check-python
	$(PYTHON) -m pip install --user --break-system-packages -r requirements.txt -r requirements-dev.txt

venv: check-python
	$(PYTHON) -m venv .venv

install-venv: venv
	. .venv/bin/activate && python -m pip install --upgrade pip && python -m pip install -r requirements.txt -r requirements-dev.txt

test: check-python
	$(PYTHON) -m pytest -q -s

test-models: check-python
	$(PYTHON) -m pytest tests/test_models.py -q -s

test-golden: check-python
	$(PYTHON) -m pytest tests/test_golden_run.py -q -s

test-ralph: check-python
	$(PYTHON) -m pytest tests/ralphing_harness.py -q -s

run-movers: check-python
	$(PYTHON) -m daily_movers run --date $(DATE) --mode movers --top $(TOP) --region $(REGION) --out $(OUT)

run-watchlist: check-python
	$(PYTHON) -m daily_movers run --mode watchlist --watchlist $(WATCHLIST) --out $(WATCH_OUT)

run-email: check-python
	$(PYTHON) -m daily_movers run --date $(DATE) --mode movers --top $(TOP) --region $(REGION) --send-email --out $(EMAIL_OUT)

smoke: test run-movers run-watchlist

clean-runs:
	rm -rf runs/$(DATE) runs/watchlist-demo runs/email-demo runs/*-check runs/*-recheck
