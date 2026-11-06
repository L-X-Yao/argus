.PHONY: lint test build check dev clean

lint:
	ruff check backend/ scripts/ tests/
	npx svelte-check --tsconfig ./tsconfig.json

test:
	python -m pytest tests/test_unit_*.py tests/test_contract_*.py -q --tb=short
	npx vitest run

test-cov:
	python -m pytest tests/test_unit_*.py tests/test_contract_*.py -q --cov=backend --cov-report=term-missing --cov-fail-under=95
	npx vitest run --coverage

# tests/conftest.py starts its own simulator and backend.
test-integration:
	python -m pytest tests/test_integration.py tests/test_integration_rest.py -q --tb=short

build:
	npm run build

check: lint test build
	@echo "All checks passed."

dev:
	python run.py --sim

clean:
	rm -rf dist/ build/ .pytest_cache/ coverage/
