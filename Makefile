.PHONY: help validate validate-full extension-tests test install

help:
	@echo "StorageOps — Pi Coding Agent extension + skill pack"
	@echo ""
	@echo "Usage:"
	@echo "  make validate       Fast skill/extension/doc gates (no tests run)"
	@echo "  make extension-tests Run the TypeScript extension behavioral tests"
	@echo "  make validate-full  Everything runnable offline: validate + pytest + extension tests + size/routing gates"
	@echo "  make test           Run pytest, extension tests, and validation"
	@echo "  make install        Install thin CLI shim"
	@echo ""
	@echo "  Note: package_check.py, install-smoke, and diagnosis-smoke run in CI"
	@echo "        (they need a wheel build / network) — see docs/release.md."

validate:
	@echo "=== Validating skills ==="
	@python3 scripts/skill_integrity_check.py
	@python3 scripts/no_hardcoded_pricing.py
	@python3 scripts/reference_scope_check.py
	@python3 scripts/version_reference_check.py
	@echo "=== Validating extension ==="
	@test -f storageops_cli/extensions/storageops.ts && echo "  OK: extension file exists" || { echo "  FAIL: extension not found"; exit 1; }
	@grep -q "scan_secrets" storageops_cli/extensions/storageops.ts && echo "  OK: scan_secrets tool" || { echo "  FAIL: scan_secrets missing"; exit 1; }
	@grep -q "detect_domain" storageops_cli/extensions/storageops.ts && echo "  OK: detect_domain tool" || { echo "  FAIL: detect_domain missing"; exit 1; }
	@grep -q "search_memory" storageops_cli/extensions/storageops.ts && echo "  OK: search_memory tool" || { echo "  FAIL: search_memory missing"; exit 1; }
	@grep -q "capture_http_trace" storageops_cli/extensions/storageops.ts && echo "  OK: capture_http_trace tool" || { echo "  FAIL: capture_http_trace missing"; exit 1; }
	@echo "=== All validations passed ==="

extension-tests:
	@bash scripts/run_extension_tests.sh

# Everything that can run offline, mirroring the deterministic CI gates. Grepping
# the extension is not enough — the routing/provider/trace logic lives in
# TypeScript and is only covered by extension-tests.
validate-full: validate
	python3 -m pytest
	$(MAKE) extension-tests
	python3 scripts/repo_size_gate.py
	python3 scripts/routing_contract_check.py

test:
	python3 -m pytest
	$(MAKE) extension-tests
	$(MAKE) validate

install:
	pip install -e .
