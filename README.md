# voice-kiosk

A café kiosk that customers operate **with their voice only**, through a telephone-style handset.
The customer lifts the handset, an AI assistant greets them in Korean, takes the order and drives
a clean, animated display. There are no touch buttons.

This is a **demo of an idea**, not a product: payment is simulated.

- Conversation: the [Gemini Live API](https://ai.google.dev/gemini-api/docs/live) (one streaming
  session per customer: audio in, audio out, interruptions, transcripts, function calls).
- Backend: Python 3.12 (`uv`), FastAPI. It owns the order, validates every action of the model
  and enforces the safety rules (payment, discarding the order) in code.
- Display: Svelte + TypeScript, full-screen in Edge kiosk mode. It only renders what the backend
  pushes over a WebSocket.

## Status

Built in milestones (see [docs/architecture.md](docs/architecture.md#milestones)). Done:
repository and CI (1), menu data, order and kiosk flow (2), Live API check (3,
[results](docs/live-check.md)), and the assistant session with function calls and safety rules
(4), the display with its animations (5), the backend wired to the display (6), and the
handset's microphone and earpiece with barge-in (7). Run it with
`npm --prefix frontend run build` and `uv run python -m kiosk`, open <http://127.0.0.1:8765>,
press `Space` to lift the handset and talk (`F2` to type instead); audio devices are set in
`configs/settings.local.yaml`, see [docs/setup.md](docs/setup.md#the-handsets-audio).

## Screenshots

The display, driven by recorded events (`?demo=order`, `?demo=allergy`; more in
[docs/screenshots](docs/screenshots)):

| | | |
|---|---|---|
| ![Start](docs/screenshots/start.jpg) | ![Recommended items](docs/screenshots/recommended.jpg) | ![An item and its required choices](docs/screenshots/item.jpg) |
| ![Allergy-safe items](docs/screenshots/allergy.jpg) | ![Card terminal](docs/screenshots/payment.jpg) | ![Order number](docs/screenshots/done.jpg) |

## Quick start

See [docs/setup.md](docs/setup.md) for details.

```bash
uv sync
npm --prefix frontend ci
cp .env.example .env   # then put your own GEMINI_API_KEY in .env
uv run pytest
```

## Repository layout

| Path | What |
|---|---|
| `kiosk/domain/` | Menu, order and kiosk flow. Pure Python, fully tested. |
| `kiosk/assistant/` | The Live session, instructions, function declarations, safety rules. |
| `kiosk/voice/` | Audio devices (handset mic and earpiece) and the hook switch. |
| `kiosk/server/` | Wiring and the WebSocket server for the display. |
| `frontend/` | The display (Svelte). |
| `data/` | `menu.yaml`, `cafe.yaml` and `images/<item_id>.png`: edit these to change the menu. |
| `configs/` | `settings.yaml`; personal overrides go in git-ignored `settings.local.yaml`. |
| `docs/` | [Architecture](docs/architecture.md), [decisions](docs/decisions.md), [setup](docs/setup.md), [Live API check](docs/live-check.md). |

## Contributing

Branch → pull request → review. See [CONTRIBUTING.md](CONTRIBUTING.md).
This repository is **public**: never commit API keys, `.env`, `*.local.yaml`, recordings or logs.
