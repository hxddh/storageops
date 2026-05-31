.PHONY: install install-dev install-api install-mcp test lint serve mcp clean help

PYTHON ?= python3
VENV   ?= .venv
PIP    = $(VENV)/bin/pip
PYTEST = $(VENV)/bin/pytest
STORAGEOPS = $(VENV)/bin/storageops

help:
	@echo "StorageOps — object storage diagnostic toolkit"
	@echo ""
	@echo "Usage:"
	@echo "  make install       Install CLI (production)"
	@echo "  make install-dev   Install CLI + dev dependencies (recommended for contributors)"
	@echo "  make install-api   Install CLI + FastAPI web server extras"
	@echo "  make install-mcp   Install CLI + MCP server extras"
	@echo "  make test          Run full test suite"
	@echo "  make lint          Run ruff linter"
	@echo "  make serve         Start web UI and API server (port 8080)"
	@echo "  make mcp           Start MCP stdio server"
	@echo "  make eval          Run golden case evaluation (no Pi required)"
	@echo "  make clean         Remove build artifacts and cache files"

$(VENV):
	$(PYTHON) -m venv $(VENV)

install: $(VENV)
	$(PIP) install -e storageops-cli/

install-dev: $(VENV)
	$(PIP) install -e "storageops-cli/[dev]"

install-api: $(VENV)
	$(PIP) install -e "storageops-cli/[api]"

install-mcp: $(VENV)
	$(PIP) install -e "storageops-cli/[mcp]"

test: $(VENV)
	cd storageops-cli && $(PYTEST) ../storageops-core/tests/ tests/ -v

lint: $(VENV)
	$(VENV)/bin/ruff check storageops-cli/ storageops-core/

serve: $(VENV)
	$(STORAGEOPS) serve --host 127.0.0.1 --port 8080

mcp: $(VENV)
	$(STORAGEOPS) mcp

eval: $(VENV)
	cd storageops-cli && $(STORAGEOPS) eval --all

clean:
	rm -rf $(VENV) storageops-cli/build/ storageops-cli/*.egg-info
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
