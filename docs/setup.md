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

## Changing the menu, cafe info and images

- **Menu**: edit `data/menu.yaml` (items, prices, descriptions, ingredients, allergens, options).
  The comments at the top explain every field.
- **Cafe info** (hours, Wi-Fi, restroom, ...): edit `data/cafe.yaml`. The assistant answers
  questions only from these two files.
- **Images**: drop `data/images/<item id>.png` (or `.webp`, `.jpg`), e.g. `americano.png`.
  Square images look best. Items without an image show their emoji.
- When you have checked an invented fact, set its `verified: true`.

Then check the data; it prints mistakes, the facts not verified yet and which items have images:

```bash
uv run python -m kiosk.domain.check
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

The display and the handset come in milestones 6 and 7. Until then:

**Typed conversation in the terminal** (real Live API, audio muted): one customer session per
handset lift; type what the customer says.

```bash
uv run python -m kiosk.assistant.chat
```

`/order` prints the order, `/hangup` ends the session (a new customer starts), `/quit` exits.
The assistant's words, the screen it chose and the payment steps are printed.

**The display with fake events** (no backend needed): it plays recorded timelines of a real
kiosk session.

```bash
npm --prefix frontend run dev
```

Then open <http://localhost:5173/?demo=order> (an order from greeting to payment) or
`?demo=allergy` (allergy question, item details, Wi-Fi card, an interruption, a connection
notice). Add `&at=21500&pause` to freeze at a moment (ms), `&dev` to open the developer panel
(also `F2`), `&cursor` to show the mouse pointer. After changing the menu data or the event
format, regenerate the timelines:

```bash
uv run python scripts/make_demo_events.py
```

**Live API checks** (milestone 3): `uv run python scripts/live_check.py --help`, results in
[live-check.md](live-check.md). `mic` mode lets you talk to the assistant through any headset.

## Troubleshooting

- **`[WinError 4551]` / "애플리케이션 제어 정책에서 이 파일을 차단했습니다"**: Windows Smart App
  Control blocks newly generated, unsigned `.exe` launchers. For a pre-commit hook, running it
  again helped. The project defines no console-script launchers for this reason: run its tools
  with `uv run python -m ...`.
- **`uv` warns about `C:\msys64\...\python.exe`**: harmless; the project uses uv's own Python 3.12
  (`python-preference = "only-managed"` in `pyproject.toml`).
