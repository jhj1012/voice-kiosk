# Contributing

## Workflow

1. Pick or create an issue on GitHub.
2. Create a branch from `main`, e.g. `feature/<short-name>`, `fix/<short-name>`, `docs/<short-name>`
   (milestones use `m<N>-<name>`).
3. Commit small, focused changes. `pre-commit` runs ruff, the import rules and the frontend lint.
4. Open a pull request to `main`. At least one teammate reviews it.
5. CI must pass (Python lint, import rules, tests; frontend lint, type check, tests, build)
   before merging.

## Rules

- **Layers** (checked by `lint-imports`): `kiosk.server` may import everything;
  `kiosk.assistant` and `kiosk.voice` never import each other or `kiosk.server`;
  `kiosk.domain` is pure (no network, audio or web framework) and imports only `kiosk.config`.
- **Safety rules live in code**, not only in the prompt: paying and discarding the order are
  checked in `kiosk/assistant/` and covered by tests. Do not weaken them without a decision in
  [docs/decisions.md](docs/decisions.md).
- **Tests** must not need a microphone, speaker, network or browser. Mock the Live session.
- **The display only renders state** pushed by the backend; business logic stays in Python.
- **Menu data** lives in `data/`. Facts that nobody has checked yet carry `verified: false`.
- **Secrets**: never commit API keys, `.env`, `*.local.yaml`, recordings or logs. This repository
  is public: a key that was pushed once must be revoked, not just deleted.
- **Dependencies**: discuss new ones in the PR. Python: `uv add <package>` (or `--dev`) and
  commit `uv.lock`. Frontend: `npm install` in `frontend/` and commit `package-lock.json`.
- Changing the Live model or its settings: edit `configs/settings.yaml` in a PR and record why in
  `docs/decisions.md`.
