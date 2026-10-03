# Decision log

New decisions go at the end of the relevant table with the reason. Decisions carried over from the
earlier prototype ([jhj1012/kiosk-ai](https://github.com/jhj1012/kiosk-ai)) say so.

## Product

| Area | Decision | Reason |
|---|---|---|
| Interaction | **Voice only**, through a telephone-style handset (mic at the mouth, earpiece at the ear). No touch buttons. | The idea we demo. A handset also keeps the customer's voice close to the mic and the assistant's voice away from it (less echo, better barge-in). |
| Session start/end | Lifting the handset (off-hook) starts a session; hanging up (on-hook) ends it and clears the order. | Clear, physical start and end of each customer; no guessing who the next customer is (the old prototype needed timeouts and a "new customer?" question for that). |
| Hook switch | Simulated with the Space key in the display, behind a `HookSwitch` interface. | The hardware does not exist yet; a USB handset or microcontroller can replace it without touching the rest. |
| Assistant | Built into the kiosk: it knows the whole menu and flow and acts through function calls. | Replaces the old design (an external assistant reading another app's screen through Windows UI Automation), which was slow and fragile. |
| Display content | **The assistant decides what the screen shows**: display functions take any set of items and a heading (e.g. allergy-safe items), plus item details and cafe-info cards. | Requested by the team: the screen should follow the conversation. Allergen filtering is done by code from the data, not by the model. |
| Menu data | Same items, prices, option groups and option prices as the old prototype, now in `data/menu.yaml` with Korean descriptions, ingredients and tags (recommended, caffeine, sweetness, allergens). Option groups are marked required (temperature, size) or optional. Unchecked facts carry `verified: false`. | YAML allows comments and is easier to edit by hand than JSON. Invented demo facts must be easy for the team to find and review. |
| Required vs optional options | The assistant asks only required options (temperature, size); extras (shots, syrups, toppings, tumbler) only when the customer asks. | Carried over: customers found extra questions tiresome; required choices must come from the customer. |
| Discounts and stamps | **Dropped** for the demo. | Stamps need a phone number, which the customer would have to say out loud in a café; coupons add a flow with little demo value. Possible later features. |
| Payment | Simulated: "카드를 단말기에 꽂아 주세요" → "결제 중..." → done with an order number. | Demo, no real terminal. |
| Language | Korean (customers); code, docs and model instructions in English. | Carried over. |

## Technology

| Area | Decision | Reason |
|---|---|---|
| Language | Python 3.12 | Carried over: the team knows Python; old modules (cart logic, audio, Gemini client) can be reused. |
| Package manager | `uv` + `pyproject.toml` + `uv.lock` (uv's own Python: `python-preference = "only-managed"`) | Carried over: identical dependency versions for every teammate. |
| Voice conversation | **Gemini Live API**, one streaming session per customer: audio in/out, built-in voice detection and interruption (barge-in), transcripts of both sides, function calling. Model `gemini-3.8-live` (stable, Google's default for voice agents; `gemini-3.8-live-extended-thinking` is tested as an alternative). | Replaces the old pipeline (separate Gemini speech-to-text call + agent call + Windows SAPI voice), which needed several requests per turn against the free tier's ~15 requests/min, could not be interrupted, and had several seconds of latency. **Verified in milestone 3** ([live-check.md](live-check.md)): ~1.2–1.6 s from the end of speech to the first audio, barge-in in ~0.4 s, function calls reliable apart from rule slips that code checks catch. The extended-thinking variant was rejected: its function calls come ~10 s late. |
| Actions | Function calling (Live API), with flat enum parameters. | The Live API's way to act. The old prototype preferred schema-constrained JSON because *local* models broke tool calls; milestone 3 measures function-call reliability with Gemini Live. |
| Safety | Safety rules live in code: pay only after the customer asked to pay (in their own transcribed words) and the order and total were read back with the cart unchanged since; clear the order only after the customer's confirmed yes (hanging up is the exception). No extra "결제하시겠어요?" question: the read-back is a statement. | Carried over: in the old prototype's tests, prompt rules alone were not enough (the model pressed a button that emptied the cart to "go back"). |
| Voice detection and transcription | Server voice detection with `start_of_speech_sensitivity: HIGH` and `prefix_padding_ms: 300`; input transcription with `language_codes: [ko-KR]` and the menu names as `custom_vocabulary`. | Measured in milestone 3: with the defaults, short answers ("레귤러요") were missed, first syllables were clipped and transcripts sometimes switched language. |
| Typed input | `send_realtime_input(text=...)` into the same Live session. | Faster than `send_client_content` (median 1.2–1.5 s vs 2.25 s to the first audio) with the same results. Typed text interrupts the assistant like speech does. |
| Payment flow | One `request_payment()` call: code checks that the customer asked to pay, shows the review and returns a read-back written by code; **code starts the card terminal** after the assistant's spoken turn contains the total. Replaces the planned `review_order` + `start_payment` (milestone 4). | In the milestone 3 check the model said the read-back but forgot `start_payment` in 4 runs, and once started the payment unasked. Now the model cannot skip or rush the step. |
| Required options must be heard | A temperature or size from the model is set only if the customer's words contain that choice (name, `say` text or `aliases` in `menu.yaml`); otherwise it is left out and the model is told to ask. | In the milestone 3 check the model chose Large from a half-heard sentence. Aliases (아아, 뜨아, 큰 거, ...) are data, so the team can add words. |
| Voice | `Sulafat` (prebuilt Live voice). | Picked by the team from eight samples (milestone 3). |
| Transcription language | Input and output transcription with `language_codes: [ko-KR]`; pieces mostly in another script are dropped from the transcript. | Once, a Hindi paragraph was appended to the transcript of a Korean greeting; never shown to customers. |
| Session limits | One Live session per customer; session resumption, `GoAway` handling and context compression; on a restart the new session gets the current order. | Live connections last ~10 min and audio sessions 15 min; an order takes 1–3 min. |
| Audio I/O | In the backend with `sounddevice`; handset devices chosen in `configs/settings*.yaml` by name or index. 16 kHz in, 24 kHz out. | The API key and audio stay out of the browser; no browser mic permissions; reuses the old device code. Risk: echo from the earpiece into the mic; measured in milestone 7 (an energy gate while speaking if needed). |
| Backend server | FastAPI + uvicorn, one WebSocket; serves the built display. | Small, async (fits the Live session), easy to test without a network. |
| Display | Svelte 5 + TypeScript + Vite; Svelte's built-in transitions (`crossfade`, `flip`); Pretendard font bundled. Full-screen with Microsoft Edge `--kiosk`. | Clean, smooth animations without a motion library; Edge is on every Windows 11 PC (no pywebview). The display only renders state pushed by the backend. |
| Avatar | None yet: an animated "presence" (idle, listening, thinking, speaking) behind a component slot. | A real avatar comes later. |
| Menu images | Empty at first; drop `data/images/<item_id>.png` (or jpg/webp). Placeholder: the item's emoji on a gradient. | Images will be AI-generated later; adding one needs no code change. |
| Developer mode | Typed Korean goes into the same Live session (audio can be muted). | Everything can be tested without a handset. |
| Architecture rules | `server` > (`assistant` \| `voice`) > `domain` > `config`; `domain` is pure. Enforced by `import-linter`. | Keeps the order logic testable and the audio/AI parts swappable. |
| Tests | No mic, speaker, network or browser; the Live session is mocked. | Carried over: runs in CI. |

## Gemini API, privacy and secrets

| Area | Decision | Reason |
|---|---|---|
| Free tier | Development on the free tier: ~15 requests/min and 500 requests/day per model for normal models; Live API limits are shown in AI Studio and measured in milestone 3. | Carried over (the old agent model hit the daily cap during testing). |
| Privacy: audio | The customer's voice and the conversation are sent to Google. On the free tier Google says the data is **used to improve its products**. Nothing is saved locally unless a developer turns recording on (git-ignored `recordings/`); logs hold text only (git-ignored `logs/`). | No local model is good enough on our PCs (old measurement: local 7B/14B models took 8–25 s per step). A real deployment would need the paid tier and a privacy notice. |
| Secrets | API key in `GEMINI_API_KEY` (environment or git-ignored `.env`), backend only, never in the browser. | Carried over; each teammate uses their own key. |
| Repo | **Public**, `jhj1012/voice-kiosk`. | Anyone can read the code and its history. Never commit API keys, `.env`, `*.local.yaml`, recordings or logs; a secret that was pushed once must be revoked. |

## Reference hardware

Carried over: laptop with 32 GB RAM and an Intel Arc 140V integrated GPU (16 GB shared memory).
This is why the project uses the Gemini API instead of local models.
