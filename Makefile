.PHONY: help validate install

help:
	@echo "StorageOps — Pi Coding Agent extension + skill pack"
	@echo ""
	@echo "Usage:"
	@echo "  make validate       Validate skills and extension"
	@echo "  make install        Install thin CLI shim"

validate:
	@echo "=== Validating skills ==="
	@python3 scripts/skill_integrity_check.py
	@echo "=== Validating extension ==="
	@test -f storageops_cli/extensions/storageops.ts && echo "  OK: extension file exists" || { echo "  FAIL: extension not found"; exit 1; }
	@grep -q "scan_secrets" storageops_cli/extensions/storageops.ts && echo "  OK: scan_secrets tool" || { echo "  FAIL: scan_secrets missing"; exit 1; }
	@grep -q "detect_domain" storageops_cli/extensions/storageops.ts && echo "  OK: detect_domain tool" || { echo "  FAIL: detect_domain missing"; exit 1; }
	@grep -q "search_memory" storageops_cli/extensions/storageops.ts && echo "  OK: search_memory tool" || { echo "  FAIL: search_memory missing"; exit 1; }
	@echo "=== All validations passed ==="

install:
	pip install -e .
