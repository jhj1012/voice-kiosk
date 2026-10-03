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

Built in milestones (see [docs/architecture.md](docs/architecture.md#milestones)).
Milestones 1 (repository skeleton and CI) and 2 (menu data, order and kiosk flow) are in place.

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
| `docs/` | [Architecture](docs/architecture.md), [decisions](docs/decisions.md), [setup](docs/setup.md). |

## Contributing

Branch → pull request → review. See [CONTRIBUTING.md](CONTRIBUTING.md).
This repository is **public**: never commit API keys, `.env`, `*.local.yaml`, recordings or logs.
