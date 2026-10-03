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
3. **Review → paying → done**: `review_order` shows the order and returns a read-back written by
   code; `start_payment` is checked by the safety gate; the simulated card terminal runs; the
   done screen shows the order number.
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

## Function declarations

Options are flat enum fields (`temperature`, `size`, `shot`, `syrup`, `whipped_cream`, `tumbler`);
code checks which apply to each item. Every call returns a short JSON result; refused calls
return `"BLOCKED: <reason>"`.

The **assistant decides what the screen shows**: the display tools take any set of items and a
heading, so the screen can follow the conversation (e.g. "우유가 들어가지 않은 메뉴" for a customer
with a milk allergy).

| Tool | Effect / rules in code |
|---|---|
| `show_menu(title?, category?, item_ids?, highlight_ids?, exclude_allergens?)` | Shows a chosen set of items (or a category, or everything) under a heading, with highlighted recommendations. `exclude_allergens` is filtered by code from the data, and the result lists what was removed. Display only. |
| `show_item(item_id)` | Shows one item's details (description, ingredients, allergens, options) without ordering. |
| `show_info(topic)` | Shows a cafe-info card (Wi-Fi, restroom, hours, ...; topics come from `cafe.yaml`). |
| `choose_item(item_id, quantity?, options…)` | The item becomes the pending item (its image enlarges). Once every **required** option is known it is added to the order automatically; otherwise the result lists the missing groups and the screen shows their choices. |
| `set_options(options…, quantity?)` | Fills in the pending item (same rules). |
| `cancel_item()` | Drops the pending item. |
| `change_line(line, quantity?, options…)` | Changes an order line; quantity 0 removes it. |
| `set_dining(choice: here \| to_go)` | Dine-in or take-out. |
| `review_order()` | Shows the review and returns a read-back written by code (items, options, quantities, dining, total) that the model must say. Remembers the reviewed cart version. |
| `start_payment()` | **Blocked unless**: the cart is not empty, dining is chosen, the reviewed version equals the current cart, the model finished a spoken turn after the review, and the **customer's own transcribed words** asked to pay (pay phrases, or a yes to a payment question). |
| `cancel_order(confirmed)` | **Blocked unless** the customer's latest transcribed words are a yes to the assistant's confirm question. Hanging up clears the order without asking. |

Questions ("디카페인 돼요?", "많이 달아요?", "화장실 어디예요?") are answered from the menu and cafe
data in the instructions; if the data does not say, the assistant says so.

## WebSocket events

One WebSocket at `/ws`. Backend → display:

```jsonc
{"type": "init", "menu": {...}, "cafe": {...}}       // on connect; items carry image_url when a file exists
{"type": "state", "seq": 42,
 "phase": "idle|ordering|paying|done",
 "assistant": "idle|connecting|listening|thinking|speaking",
 "view": {"screen": "attract|welcome|menu|item|info|review|payment|done",
          "title": "우유가 들어가지 않은 메뉴", "item_ids": ["americano", "..."],
          "highlight": ["cafe_latte"], "item_id": "americano", "topic": "wifi"},
 "pending": {"item_id": "americano", "quantity": 1, "chosen": {"size": "large"},
             "missing": ["temperature"]},
 "order": {"lines": [{"line": 1, "item_id": "americano", "name": "아메리카노",
                      "options": "ICE, Large", "quantity": 2, "total": 9000}],
           "dining": "to_go", "total": 9000},
 "payment": {"step": "insert_card|processing|approved", "order_number": 17}}
{"type": "subtitle", "speaker": "customer|assistant", "turn": 12, "text": "...", "final": false}
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

## Display states and animations

- **Attract**: slow gradient, cafe name, "수화기를 들고 말씀해 주세요", gentle breathing.
- **Assistant presence**: `<AssistantPresence state level>` (orb + rings): idle breathes,
  connecting spins, listening follows the mic level, thinking orbits, speaking follows the output
  level. A real avatar can replace it later behind the same props.
- **Menu**: the items the assistant chose, under its heading; cards stagger in, highlighted items
  glow, changes animate with `flip`.
- **Item**: the card grows into a large image (`crossfade`); minimal chips for missing required
  options; when added, the item flies into the order summary and the total counts up.
- **Order summary**: always a small corner panel; in review it moves to the center.
- **Info card**: slides in.
- **Payment**: a card slides into the terminal ("카드를 단말기에 꽂아 주세요") → spinner
  ("결제 중...") → check mark and large order number → back to attract.
- **Subtitles**: a bottom band with what was heard (lighter) and what the assistant says.
- **Developer mode** (`F2`): typed input, mute, event log. `?demo=<scenario>` plays fake events
  without a backend.

Menu images: drop `data/images/<item_id>.png` (or `.jpg`, `.webp`). Missing images show the item's
emoji on a soft gradient tile.

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
