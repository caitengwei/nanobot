# Repository Guidelines

## Project Structure & Module Organization

`nanobot/` is the Python package: `agent/` for the LLM/tool loop, `agent/tools/` for built-in tools, `bus/` for message routing, `channels/` for chat integrations, `providers/` for LLM adapters, `config/` for settings, `cli/` for commands, and `templates/` plus `skills/` for bundled workspace content. Tests mirror modules under `tests/`. `bridge/` contains the Node 20+ WhatsApp bridge; `case/` holds demos; `docs/` holds design notes.

## Architecture & Runtime Notes

Message flow: `Channel -> InboundMessage -> MessageBus -> AgentLoop -> ContextBuilder/Provider/ToolRegistry -> OutboundMessage`. Runtime workspaces load `AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, and `memory/`; update defaults in `nanobot/templates/`.

## Build, Test, and Development Commands

- `uv sync --all-extras`: install Python dependencies and extras.
- `pip install -e ".[dev]"`: editable install without `uv`.
- `uv run pytest tests/` or `pytest`: run Python tests.
- `pytest tests/channels/test_slack_channel.py` or `pytest -k "test_onboard"`: run focused tests.
- `ruff check nanobot tests`: lint imports, names, and style.
- `ruff check --fix nanobot tests`: apply lint fixes.
- `ruff format nanobot tests`: apply Ruff formatting.
- `cd bridge && npm install && npm run build`: compile the WhatsApp bridge.
- `nanobot onboard` / `nanobot agent`: initialize config and run the CLI assistant.

## Coding Style & Naming Conventions

Target Python 3.11+. Use 4-space indentation, type annotations for public interfaces, Pydantic v2 for structured config/data, `asyncio` for async flows, and Loguru for logging. Ruff uses 100-character lines, rules `E`, `F`, `I`, `N`, and `W`, with `E501` ignored. Use `snake_case` for functions/modules and `PascalCase` for classes such as `SlackChannel`.

## Testing Guidelines

Pytest is the test framework; `asyncio_mode = "auto"` is enabled. Put new tests near covered behavior and name files `test_*.py`. Prefer focused unit tests for tools, providers, config, and channel handling. Shared agent-loop or channel-manager changes need regression tests in `tests/agent/` or `tests/channels/`.

## Commit & Pull Request Guidelines

History uses Conventional Commit style with scopes, for example `fix(slack): sanitize attachment filename` or `test(slack): rename test`. Keep commits focused and use a feature branch plus PR; do not push directly to `main`. Target `main` for bug fixes/docs and `nightly` for features or risky refactors. PRs should summarize behavior changes, tests run, linked issues, and screenshots/log snippets for user-visible CLI or channel changes. This fork expects PRs against `caitengwei/nanobot`.

## Security & Configuration Tips

Do not commit secrets, tokens, or real workspace data. Local config lives in `~/.nanobot/config.json`; keep examples sanitized. Follow `SECURITY.md` for vulnerability reports.
