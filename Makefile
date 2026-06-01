.PHONY: install install-dev install-api install-mcp test lint serve mcp clean eval help

PYTHON ?= python3
VENV   ?= .venv
PIP    = $(VENV)/bin/pip
PYTEST = $(VENV)/bin/pytest
STORAGEOPS = $(VENV)/bin/storageops

help:
	@echo "StorageOps — S3-compatible object storage diagnostic agent"
	@echo ""
	@echo "Usage:"
	@echo "  make install       Install (production)"
	@echo "  make install-dev   Install + dev dependencies"
	@echo "  make install-api   Install + FastAPI extras"
	@echo "  make install-mcp   Install + MCP extras"
	@echo "  make test          Run test suite"
	@echo "  make lint          Run ruff linter"
	@echo "  make serve         Start web UI (port 8080)"
	@echo "  make mcp           Start MCP server"
	@echo "  make eval          Run golden case evaluation"
	@echo "  make clean         Remove build artifacts"

$(VENV):
	$(PYTHON) -m venv $(VENV)

install: $(VENV)
	$(PIP) install -e .

install-dev: $(VENV)
	$(PIP) install -e ".[dev]"

install-api: $(VENV)
	$(PIP) install -e ".[api]"

install-mcp: $(VENV)
	$(PIP) install -e ".[mcp]"

test: $(VENV)
	cd storageops && $(PYTEST) tests_core/ -v

lint: $(VENV)
	$(VENV)/bin/ruff check storageops/

serve: $(VENV)
	$(STORAGEOPS) serve --host 127.0.0.1 --port 8080

mcp: $(VENV)
	$(STORAGEOPS) mcp

eval: $(VENV)
	$(STORAGEOPS) eval --all

clean:
	rm -rf $(VENV) build/ *.egg-info storageops.egg-info
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
