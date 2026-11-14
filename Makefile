.PHONY: help validate validate-full ci-local ci-full extension-tests test-fast test install dev live-smoke package-check contract mock-e2e

help:
	@echo "StorageOps — Pi Coding Agent extension + skill pack"
	@echo ""
	@echo "Usage:"
	@echo "  make validate       Fast skill/extension/doc gates (no tests run)"
	@echo "  make ci-local       Offline PR gate (mirrors CI validate job; run before PR)"
	@echo "  make validate-full  Alias for ci-local"
	@echo "  make ci-full        ci-local + package-check (pre-release)"
	@echo "  make test           Alias for ci-local"
	@echo "  make test-fast      pytest + extension tests + fast validate only"
	@echo "  make extension-tests Run the TypeScript extension behavioral tests"
	@echo "  make install        Install thin CLI shim (pip install -e .)"
	@echo "  make dev            One-shot dev setup (scripts/dev_setup.sh; DEV_SETUP_FLAGS=...)"
	@echo "  make live-smoke     Model smoke + 5 golden-case live diagnoses (needs API key)"
	@echo "  make package-check  Build wheel and run package_check.py (needs network once)"
	@echo "  make contract       Regenerate the extension root-cause table from contract/"
	@echo "  make mock-e2e       End-to-end launch test (wheel -> install -> Pi, needs npm once)"
	@echo ""
	@echo "  Note: install-smoke and diagnosis-smoke run in CI when configured"
	@echo "        (wheel install / STORAGEOPS_MODEL_KEY) — see docs/release.md."

validate:
	@echo "=== Validating skills ==="
	@python3 scripts/skill_integrity_check.py
	@python3 scripts/no_hardcoded_pricing.py
	@python3 scripts/reference_scope_check.py
	@python3 scripts/version_reference_check.py
	@echo "=== Validating extension ==="
	@test -f storageops_cli/extensions/storageops/index.ts && echo "  OK: extension file exists" || { echo "  FAIL: extension not found"; exit 1; }
	@test -f storageops_cli/extensions/storageops/contract.generated.ts && echo "  OK: contract table present" || { echo "  FAIL: contract.generated.ts missing (run make contract)"; exit 1; }
	@for tool in scan_secrets detect_domain search_cases probe_endpoint probe_bucket probe_capabilities run_analyzer capture_http_trace submit_diagnosis; do 		grep -q "name: \"$$tool\"" storageops_cli/extensions/storageops/index.ts && echo "  OK: $$tool tool" || { echo "  FAIL: $$tool missing"; exit 1; }; 	done
	@echo "=== All validations passed ==="

extension-tests:
	@bash scripts/run_extension_tests.sh

# Mirrors .github/workflows/ci.yml validate job (everything offline).
contract:
	python3 scripts/gen_contract.py

ci-local: validate
	python3 scripts/provider_scope_check.py
	python3 scripts/contract_check.py
	python3 scripts/root_cause_contract_check.py
	python3 scripts/coverage_check.py
	python3 skills/storageops-eval-golden-cases/scripts/golden_case_validator.py \
		skills/storageops-eval-golden-cases/cases
	python3 -m pytest
	$(MAKE) extension-tests
	python3 scripts/repo_size_gate.py
	python3 scripts/routing_contract_check.py
	python3 skills/storageops-eval-golden-cases/scripts/eval_all.py \
		--cases skills/storageops-eval-golden-cases/cases \
		--outputs skills/storageops-eval-golden-cases/baseline-outputs \
		--only-with-outputs

validate-full: ci-local

test: ci-local

test-fast:
	python3 -m pytest
	$(MAKE) extension-tests
	$(MAKE) validate

ci-full: ci-local
	$(MAKE) package-check

install:
	pip install -e .

dev:
	@bash scripts/dev_setup.sh $(DEV_SETUP_FLAGS)

live-smoke:
	@bash scripts/live_smoke.sh

mock-e2e:
	@bash scripts/e2e_mock_test.sh

package-check:
	python3 -m pip install --upgrade pip build
	python3 scripts/prepare_httpmon_vendor.py
	python3 -m build --wheel
	python3 scripts/package_check.py
