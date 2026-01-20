# Repository Guidelines

## Project Structure & Module Organization
- `app/` split into `api` (FastAPI routers/schemas), `application` (use cases + interfaces), `infrastructure` (db, gateways, in-memory repos), and `domain` (shared constants).
- `tests/` holds pytest suites for endpoints, workers, schemas; mirror module names in new files (`test_*.py`).
- `spec/` captures architecture, contracts, implementation gaps; `prompts/` stores agent instructions/templates referenced during slices.
- `pyproject.toml` + `uv.lock` define deps; `.env.example` shows `USE_IN_MEMORY` vs `DATABASE_URL` and Stripe keys.

## Setup, Run, Build, Test Commands
- Install deps/venv with uv: `uv sync` (creates `.venv/`).
- Run API locally (in-memory default): `uv run uvicorn app.main:app --reload --port 8000`.
- Switch to MySQL: set `USE_IN_MEMORY=false` and `DATABASE_URL=mysql+aiomysql://...`; real Stripe needs `STRIPE_SECRET_KEY`.
- Lint/format: `uv run ruff check app tests` then `uv run ruff format app tests` (line length 100, rules E,F,I,B).
- Tests: `uv run pytest -q` or target a file `uv run pytest tests/test_create_reservation_endpoint.py -k <case>`.
- Build distributables (hatch backend): `uv build`.

## Coding Style & Naming Conventions
- Python 3.13 target; 4-space indent; keep functions and schemas fully typed; prefer explicit value objects/DTOs over ad-hoc dicts.
- Respect layer boundaries: `api` for validation/wiring, `application` for orchestration, `infrastructure` for I/O, `domain` stays free of framework code.
- Modules stay snake_case; request/response schemas end with `Request`/`Response`; keep idempotency handling explicit and logged.
- Run ruff before pushing; avoid exceeding 100-char lines; keep business rules aligned with `spec/*.md`.

## Testing Guidelines
- Place new tests under `tests/` with `test_*` files and functions; cover happy path plus idempotency, conflicts, webhook/outbox flows.
- Default in-memory stack requires no DB; for SQL-backed runs set `USE_IN_MEMORY=false` and point `DATABASE_URL` to a clean schema.
- Include fixtures/assertions for snapshots returned in responses (reservation_code, payment status, supplier codes).

## Commit & Pull Request Guidelines
- Use short, imperative commit titles; Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`) are preferred when possible.
- PRs: describe scope, link to issue/spec section, note env flags used (`USE_IN_MEMORY`, `DATABASE_URL`, Stripe keys), and paste `pytest`/`ruff` results.
- Keep changes small and consistent with the vertical-slice docs in `spec/`; update docs/tests when endpoints or flows change.
