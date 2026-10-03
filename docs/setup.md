# Setup

Windows 11 is the target (the kiosk PC); development also works on macOS and Linux.

## Tools

| Tool | Version | Install |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 0.12+ | `winget install astral-sh.uv` |
| [Node.js](https://nodejs.org/) | 24 LTS | `winget install OpenJS.NodeJS.LTS` |
| git, [gh](https://cli.github.com/) | recent | `winget install Git.Git GitHub.cli` |

uv downloads Python 3.12 itself; you do not need to install Python.

## First time

```bash
git clone https://github.com/jhj1012/voice-kiosk.git
cd voice-kiosk
uv sync                    # Python environment from uv.lock
npm --prefix frontend ci   # frontend packages from package-lock.json
uv run pre-commit install  # lint before every commit
cp .env.example .env       # then put your own key in .env
```

Get a Gemini API key at [Google AI Studio](https://aistudio.google.com/apikey) and put it in `.env`
as `GEMINI_API_KEY=...`. Each teammate uses their own key. `.env` is git-ignored: never commit it.
AI Studio also shows your project's real rate limits.

## Personal settings

Copy only the values you change into `configs/settings.local.yaml` (git-ignored), e.g. your
handset's audio devices:

```yaml
audio:
  input_device: "Headset"   # part of the device name, or its index
  output_device: "Headset"
```

## Checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run lint-imports
uv run pytest
npm --prefix frontend run lint
npm --prefix frontend run check
npm --prefix frontend test
npm --prefix frontend run build
```

## Running the kiosk

Added in later milestones (backend server, display in Edge kiosk mode, typed developer mode).

## Troubleshooting

- **`[WinError 4551]` from a pre-commit hook** (Windows Smart App Control blocked a program that
  pre-commit just built): run the hooks again. It passed on the second run here.
- **`uv` warns about `C:\msys64\...\python.exe`**: harmless; the project uses uv's own Python 3.12
  (`python-preference = "only-managed"` in `pyproject.toml`).
