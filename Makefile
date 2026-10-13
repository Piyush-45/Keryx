PY_PACKAGES := api workers/voice workers/postcall workers/campaigns packages/shared/python packages/db

.PHONY: sync lint format typecheck test check codegen codegen-check

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

GENERATED := packages/shared/python/vp_shared/generated packages/shared/ts/src/generated

# Regenerate Pydantic + zod from packages/shared/agent_config.schema.json.
codegen:
	uv run datamodel-codegen
	pnpm --filter @vp/shared codegen

# CI: fail if committed generated code differs from a fresh codegen run.
codegen-check: codegen
	@if ! git diff --quiet -- $(GENERATED) || [ -n "$$(git ls-files --others --exclude-standard -- $(GENERATED))" ]; then \
		echo "Generated code is stale. Run 'make codegen' and commit the result."; \
		git --no-pager diff --stat -- $(GENERATED); git ls-files --others --exclude-standard -- $(GENERATED); exit 1; \
	fi
