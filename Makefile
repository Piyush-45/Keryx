PY_PACKAGES := api workers/voice workers/postcall workers/campaigns packages/shared/python

.PHONY: sync lint format typecheck test check

sync:
	uv sync --all-packages
	pnpm install

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

# One mypy run per package: test modules share names across packages.
typecheck:
	@for p in $(PY_PACKAGES); do echo "mypy $$p"; (cd $$p && uv run mypy --config-file $(CURDIR)/pyproject.toml .) || exit 1; done

test:
	uv run pytest

check: lint typecheck test
