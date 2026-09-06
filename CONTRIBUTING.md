# Contributing to Chiant

Thanks for helping improve Chiant (urban parking detection + multi-provider payment).

## Setup

1. Install [uv](https://github.com/astral-sh/uv) and Python matching `.python-version`.
2. `uv sync`
3. Copy `.env.example` → `.env` and fill only what you need locally.
4. Run checks with `make` targets (see `Makefile`) or `uv run pytest`.

## Pull requests

- Keep PRs focused — one logical change per PR when possible.
- Prefer small commits with clear messages (`feat:`, `fix:`, `docs:`, `chore:`).
- Do not commit secrets, real API keys, or production credentials.
- Update `CHANGELOG.md` under `## Unreleased` when the change is user-visible.
- Run tests before opening the PR.

## Security

Security findings: follow `SECURITY.md` — do not file public issues for vulnerabilities.
