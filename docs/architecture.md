# Architecture

## Overview

```
 handset mic ──16 kHz PCM──►┐                         ┌──► Gemini Live API (one session per customer)
                            │   kiosk (Python)        │    audio + transcripts + function calls
 handset earpiece ◄─24 kHz──┤                         │
 hook switch (Space key) ──►│  voice ─► server ◄─► assistant ─► domain (order, flow)
                            │             │ WebSocket (state, subtitles, levels)
                            └─────────────▼
                                  display (Svelte, Edge kiosk mode)
```

- **Backend** (`kiosk/`, Python 3.12): owns all state. The model can only change it through
  function calls, which code validates and executes.
- **Display** (`frontend/`): renders the state pushed over one WebSocket. It has no business
  logic. In developer mode it also sends typed text, the simulated hook and a mute switch.
- **Audio** is captured and played in the backend (`sounddevice`), so the API key and the audio
  never pass through the browser and the handset is picked by name in config.

## Layers

Checked by `lint-imports` (see `pyproject.toml`):

| Layer | May import | Contents |
|---|---|---|
| `kiosk.server` | everything | FastAPI app, WebSocket hub, event models, wiring (`main`) |
| `kiosk.assistant` | domain, config | Live connection (protocol + google-genai), session loop, instructions, function declarations, action execution, safety gates |
| `kiosk.voice` | domain, config | audio devices, mic and speaker streams, hook switch interface |
| `kiosk.domain` | config | menu, order, kiosk flow state (pure; no network, audio or web framework) |
| `kiosk.config` | — | settings from `configs/settings.yaml` (+ `settings.local.yaml`), `.env` |

`assistant` and `voice` never import each other: `server` connects mic frames to the session and
the session's audio to the speaker.

## Session lifecycle

1. **Idle**: attract screen. The hook switch reports *off-hook* → a Live session opens with the
   instructions (rules + menu + cafe info + current order) and the assistant greets the customer.
2. **Ordering**: audio streams both ways. Transcripts become subtitles. Function calls change the
   order and choose what the display shows.
3. **Payment**: the customer asks to pay → `request_payment` (checked in code) shows the review and
   returns a read-back written by code → the assistant says it → **code** starts the simulated
   card terminal once the total was heard → done screen with the order number; the assistant
   announces it (kiosk cue `[결제 완료 ...]`).
4. **On-hook** (any time): the session closes, the order is cleared, back to idle. The done screen
   also returns to idle after `flow.done_return_s`.

Live connections last about 10 minutes and audio sessions 15 minutes. The session uses session
resumption (handles are valid for 2 h), reacts to `GoAway` and enables context compression. If a
session must start over, the new one gets the current order in its instructions: the order lives
in code, not in the model's memory.

## Flow state (`kiosk.domain.flow`)

`Kiosk` holds one customer's state: `phase`, `order`, the `pending` item (the one whose options
are being asked), `view` (what the display shows) and the payment step. Every method either
changes the state (and increases `revision`) or raises `KioskError` with a message for the model.

- `phase`: `idle → ordering → paying (insert_card → processing) → done → idle`. Hanging up ends
  the session from any phase. The order is locked while paying; `cancel_payment` is possible
  until the card is "inserted".
- The **review** is a screen, not a phase: `review()` stores the order's `version`, and
  `start_payment()` is refused if the order changed since (`review_is_current`).
- An item is added as soon as every **required** option is known (`choose_item` /
  `set_options`); otherwise the item screen shows the missing choices. Optional groups keep
  their default ("기본", "없음"). A temperature or size the item has no option for is accepted
  only if it matches how the item is served (ICE for an iced-only item, Regular for one size).
- `show_menu(exclude_allergens=...)` removes items whose own allergens include one of them (in
  code, from the data). An option that adds an allergen (whipped cream: milk) does not hide the
  item; the assistant must not suggest that option.
- After payment only `show_info` is allowed ("어디서 받아요?").

## The assistant session (`kiosk.assistant.session`)

`AssistantSession` runs one customer's conversation over a `LiveConnection` (`live.py`: a small
interface with our own event types, implemented with google-genai and faked in tests). It:

- sends the greeting cue, the handset's audio and typed text (developer mode), and passes the
  assistant's audio, subtitles and state changes to a `SessionListener`;
- keeps a `Transcript` of both sides (input/output transcription, typed text) for the subtitles
  and the safety checks; transcript pieces mostly in another script are dropped (hallucinations);
- tracks the assistant's state: `connecting`, `listening`, `thinking` (the customer spoke or a
  function ran; the spoken reply after a function call comes 1–2 s later), `speaking` (until the
  received audio has been played), `idle`;
- runs each function call through the safety checks (`safety.py`) and then on the kiosk;
- starts the card terminal after the read-back, steps it (insert card → processing → approved)
  and tells the assistant the order number; ends the session after `flow.done_return_s`;
- reconnects: on `GoAway` or a dropped connection it resumes with the latest handle; if that
  fails it starts fresh with the current order in the instructions and a kiosk cue.

Text in [brackets] sent to the model is a kiosk cue, never the customer's words.
`uv run python -m kiosk.assistant.chat` runs a session in the terminal with typed input.

### Safety checks in code (`kiosk.assistant.safety`)

| Rule | How |
|---|---|
| Pay only after the customer asked | `request_payment` is blocked unless one of the customer's utterances since the items last changed (always including the latest) asks to pay: pay phrases ("결제할게요", "계산", "이게 다예요", ...), "아니요/없어요" right after the assistant asked whether they want anything else, or a yes to a payment question. Dining changes do not count as item changes. |
| Read back before paying | `request_payment` returns a read-back written by code. The terminal starts only after the assistant's next spoken turn contains the total (digits or Korean words, e.g. "만 삼천오백 원"); otherwise the assistant is reminded (twice, then it starts anyway since the total is on screen). An interruption or an item change during the read-back cancels it. |
| Discard only after a yes | `cancel_order` is blocked unless the latest customer words are a yes and the assistant's previous words asked about cancelling. |
| Required options must be heard | For `choose_item`, `set_options` and `change_line`, a new temperature or size is set only if the customer said it (the choice's name, `say` text or `aliases` in `menu.yaml`) since the item was named (or in their latest words). Otherwise it is left out and the result says `not_heard`; a call with nothing else left is blocked. |

## Function declarations

Options are flat enum fields (`temperature`, `size`, `shot`, `syrup`, `whipped_cream`, `tumbler`);
code checks which apply to each item. Every call returns a short JSON result; mistakes return
`{"error": ...}` and refused calls `{"blocked": ...}`.

The **assistant decides what the screen shows**: the display tools take any set of items and a
heading, so the screen can follow the conversation (e.g. "우유가 들어가지 않은 메뉴" for a customer
with a milk allergy).

| Tool | Effect / rules in code |
|---|---|
| `show_menu(title?, category?, item_ids?, highlight_ids?, exclude_allergens?)` | Shows a chosen set of items (or a category, or everything) under a heading, with highlighted recommendations. `exclude_allergens` is filtered by code from the data, and the result lists what was removed. Display only. |
| `show_categories()` | Shows the kinds of menu, when the customer wants to see other menus. |
| `show_item(item_id)` | Shows one item's details (description, ingredients, allergens, options) without ordering. |
| `show_info(topic)` | Shows a cafe-info card (Wi-Fi, restroom, hours, ...; topics come from `cafe.yaml`). |
| `show_order()` | Shows the whole order (display only). |
| `choose_item(item_id, quantity?, options…)` | The item becomes the pending item (its image enlarges). Once every **required** option is known it is added to the order automatically; otherwise the result lists the missing groups and the screen shows their choices. Required options nobody said are left out. |
| `set_options(options…, quantity?)` | Fills in the pending item (same rules). |
| `cancel_item()` | Drops the pending item. |
| `change_line(line, quantity?, options…)` | Changes an order line; quantity 0 removes it. |
| `set_dining(dining: here \| to_go)` | Dine-in or take-out. |
| `request_payment()` | **Blocked unless the customer asked to pay** (see above); also needs items, dining and no pending item. Shows the review and returns the read-back; code starts the terminal after it was said. |
| `cancel_payment()` | Back to ordering while the terminal waits for the card. |
| `cancel_order()` | **Blocked unless** the customer just said yes to the cancel question. Hanging up clears the order without asking. |

Questions ("디카페인 돼요?", "많이 달아요?", "화장실 어디예요?") are answered from the menu and cafe
data in the instructions; if the data does not say, the assistant says so.

## WebSocket events

One WebSocket at `/ws`. Backend → display:

```jsonc
{"type": "init", "menu": {...}, "cafe": {...}}       // on connect; items carry image_url when a file exists
{"type": "state", "seq": 42,
 "phase": "idle|ordering|paying|done",   // "review" is a screen, not a phase
 "assistant": "idle|connecting|listening|thinking|speaking",
 "view": {"screen": "attract|welcome|menu|categories|item|info|review|payment|done",
          "title": "우유가 들어가지 않은 메뉴", "item_ids": ["americano", "..."],
          "highlight": ["cafe_latte"], "item_id": "americano", "topic": "wifi"},
 "pending": {"item_id": "americano", "quantity": 1, "chosen": {"size": "large"},
             "missing": ["temperature"]},
 "order": {"lines": [{"line": 1, "item_id": "americano", "name": "아메리카노",
                      "options": "ICE, Large", "quantity": 2, "unit_price": 4500, "total": 9000}],
           "dining": "to_go", "count": 2, "total": 9000},
 "payment": {"step": "insert_card|processing|approved", "order_number": 17}}
{"type": "subtitle", "id": 12, "speaker": "customer|assistant", "text": "...", "final": false}
{"type": "level", "mic": 0.31, "out": 0.0}           // ~15/s, drives the assistant animation
{"type": "notice", "level": "info|warn|error", "text": "연결을 다시 시도하고 있어요"}
```

`state` is always a full snapshot (simple to render, safe to reconnect). Display → backend
(developer mode only):

```jsonc
{"type": "hook", "off_hook": true}      // the Space key: simulated hook switch
{"type": "dev_text", "text": "아이스 아메리카노 주세요"}
{"type": "dev_mute", "audio": false}
```

## Display: one continuous page

A portrait screen (designed for 1080×1920; on a landscape monitor it is a centered portrait
frame). White with soft blue light, flat surfaces (no shadows), as little as possible on screen.
Nothing "moves to the next screen": the assistant and the conversation stay at the top, the
order at the bottom, and in between what the assistant chose appears and disappears in place.

- **Start**: only the assistant's orb and "수화기를 들고 말씀해 주세요". When the handset is lifted
  the orb glides up and shrinks; a quiet hint of what to say appears.
- **Assistant presence**: `<AssistantPresence state level>` (orb + rings): idle breathes,
  connecting spins, listening follows the mic level, thinking orbits, speaking follows the output
  level. A real avatar can replace it later behind the same props.
- **Conversation**: under the orb, what the customer said (blue, in quotes) and what the
  assistant says; older words fade out at the top.
- **Menus**: the items the assistant chose (3–5 recommendations, a category, or a filtered set),
  no heading except a small caption for a filter or a category. Modest cards of one size
  (picture, name, price), centered; they never fill the whole screen. When the assistant shows
  other items, the cards that stay move to their new places and the others fade (`flip`).
- **Kinds of menu** (`show_categories`): four tiles of the same size, for "다른 메뉴도 보여 주세요".
- **Item**: the card's picture grows into a large image (`crossfade`); name, price, description,
  ingredients and facts; only the required choices, which fill in blue when chosen. An added item
  flies into the order bar and the total counts up.
- **Order bar**: a quiet bar at the bottom while ordering (thumbnails, count, total). The review,
  card terminal and order number appear in the middle in its place.
- **Developer mode** (`F2`): typed input, mute, event log; `Space` lifts / puts down the
  simulated handset. `?demo=order|allergy` plays recorded event timelines without a backend
  (`scripts/make_demo_events.py` records them by driving a real `Kiosk` with
  `kiosk/server/events.py`, so they always match the real event format).

The display's code (`frontend/src/`): `lib/events.ts` (event types), `lib/display.ts` (pure state
updates, unit tested), `lib/store.svelte.ts` (runes), `lib/player.ts` (demo timelines),
`lib/connection.ts` (WebSocket), `lib/components/` (`Stage` is the page; one component per kind
of content, the order bar, the assistant presence).

Menu images: drop `data/images/<item_id>.png` (or `.jpg`, `.webp`). Missing images show the item's
emoji on a soft blue tile.

## Milestones

Each milestone is its own branch with a pull request to `main`.

1. Repository skeleton + CI
2. Domain + data + tests
3. Live API check (`scripts/live_check.py`) → report and decision
4. Assistant session with typed input, function calls and safety rules + tests (mocked Live)
5. Frontend display with animations driven by fake events
6. Wiring backend ↔ frontend
7. Handset audio in/out, barge-in and the keyboard hook
8. Polish + end-to-end voice demo

## Known limitations

- **Customers who cannot speak or hear**: the kiosk is voice-only by design. Accessibility for
  them is an open question for the team.
- Needs internet; the customer's voice is processed by Google (see decisions).
- Payment, the card terminal and the hook switch are simulated.
