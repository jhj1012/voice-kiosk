# Live API check (milestone 3)

Measured on 2026-10-03 with `scripts/live_check.py` on the reference laptop over home Wi-Fi, free
tier, `gemini-3.8-live` unless noted. The real `Kiosk` and `Actions` ran behind the session.
Speech input was synthesized with the Windows Korean voice (Heami) and streamed in real time
like an open microphone. A real voice, the voice quality and real barge-in still need a person:
run `uv run python scripts/live_check.py mic` (see the end of this page).

Logs: `logs/live_check/` (git-ignored). Audio: `recordings/live_check/` (git-ignored).

## Summary

| Question | Result |
|---|---|
| Korean recognition | Synthesized speech, best settings: 6–7 of 9 phrases word-exact; the rest were understood correctly (e.g. "알레르기" → "알러지"). One clipped start in 9. Default settings were worse (see below). |
| Latency, end of speech → first audio | Median **1.2–1.6 s** (includes the server's end-of-speech detection). With a function call 1.4–2.4 s; single outliers 3–4 s. Typed text → first audio: median 1.2–1.5 s. |
| Barge-in | **3 of 3**: the server sends `interrupted` **360–450 ms** after the customer starts talking; the interruption is transcribed exactly and acted on (choose_item), reply 0.9–2.1 s after the customer stops. |
| Function calls | Typed scenarios: **91 of 104** expectations met over 4 runs (details below). Arguments were always well-formed and ids valid. |
| Typed input | Works in the same session. `send_realtime_input(text=...)`: faster (median 1.2–1.5 s to audio). `send_client_content`: 25/26 but slower (2.25 s). |
| Session limits | 5 concurrent sessions opened (we need 1). Session resumption works and keeps the conversation. ~50 sessions in ~30 minutes with no rate-limit error. About 5,200 tokens for a greeting and one order (the instructions are ~4,000). The API does not report the Live quotas; see AI Studio. |
| Extended thinking model | Unsuitable: it says a filler, then delivers the function call **~10 s** later. |

**Verdict: the Live API works for this kiosk. No fallback (STT + agent + TTS) is needed.**

## Settings that mattered

- **Server voice detection**: `start_of_speech_sensitivity: HIGH`, `prefix_padding_ms: 300`. With
  the defaults a short answer ("레귤러요") was not detected at all and "청포도" lost its first
  syllable.
- **Input transcription**: `language_codes: ["ko-KR"]` and `custom_vocabulary` (menu and option
  names). Without them the transcript sometimes switched language ("카페라떼" → "ハッピラテ",
  "우유 알레르기" → "Oi, alergia"). The model understood anyway, but subtitles and the code checks
  read the transcript.
- `speech_config.language_code: ko-KR` is accepted.

## Behaviour to design for

1. **The customer's transcript arrives before the function call**: in every turn with a call.
   The code-level safety checks can read the customer's words before running a call.
2. **The spoken reply after a function call comes as a separate turn**, 1–2 s after the function
   result. The display needs a "thinking" state for that gap.
3. **The server streams audio much faster than real time** (11 s of answer received after 2.5 s
   of playback) and tracks playback itself: on `interrupted` the kiosk must drop its playback
   buffer at once. `turn_complete` for spoken turns arrives when playback would have ended.
4. **Typed text while the assistant is speaking interrupts it**, like speech does.
5. **The model breaks rules sometimes**, so the planned code checks are needed:
   - It started the payment after "포장이요" although the customer had not asked to pay yet.
   - It took an unrelated, half-heard sentence ("가 있어") as the answer to a pending size
     question and chose Large.
   - It asked the temperature of an iced-only item once.
6. Replies are often longer than wanted for an earpiece (8–13 s for menu questions).

## Typed scenarios (function calls)

`order_and_pay`, `required_options`, `questions`, `change_and_cancel`: 26 expectations per run.
Results: 23/26, 43/52 (2 runs), 25/26 (client content). Misses:

| Miss | Times | Effect |
|---|---|---|
| Asked for the required options before calling `choose_item`, or did not record a partial answer with `set_options` (added the item correctly with both options at the end) | 7 | Order correct; the screen would not show the item and choices while asking. Prompt fix. |
| Said the read-back but did not call `start_payment` | 4 | Nothing happens after the read-back. See the payment proposal below. |
| Answered "디카페인 돼요?" and went on to ask the options as if ordering | 1 | Pushy, harmless. |

Correct every time: adding items with options and quantities, two items in one sentence,
showing the menu with highlights, the allergy filter (`exclude_allergens: ["milk"]` plus the
staff notice), the restroom card, "I don't know" for calories, changing and removing lines, and
asking before cancelling the whole order.

## Proposals for milestone 4 (need a decision)

1. **Payment as one call**: replace `review_order` + `start_payment` with `request_payment()`.
   Code checks that the customer asked to pay (their transcript), that dining is known and
   nothing is pending, shows the review and returns the read-back. **Code** starts the card
   terminal once the model has finished saying it. This keeps "read back, then pay"
   deterministic, and the model can no longer forget the second call.
2. **Required options must be heard**: when the model passes a required option (temperature,
   size), code checks that the customer's words since the item was named contain that choice
   (its name, `say` text or aliases from the data, e.g. 아이스/차가운, 라지/큰). Otherwise the call
   is blocked with "ask the customer". This stops guessed options.
3. Prompt: call `choose_item` as soon as an item is named, `set_options` for each partial answer,
   shorter replies, no temperature question for items served one way.

## Subtitles: showing what the assistant understood (milestone 8)

The customer's subtitle shows the raw transcription, e.g. "엘레 사이트로 주세요" when the customer
meant 플랫화이트. The team asked whether the screen could show what the assistant understood
instead. Measured with synthesized, deliberately mispronounced speech, 7 turns × 3 sessions per
variant (median time from the end of speech to the first audio of the reply):

| Variant | Reply | Understood text written | Problems |
|---|---|---|---|
| Today (raw transcription) | 0.86 s | — | — |
| The model calls `heard(text)` first, then goes on | 1.30 s on turns with the call (0.84 s without) | 10 of 21 turns | It skipped the call on short answers and questions |
| `heard` as a NON_BLOCKING function, answered SILENT | 1.12 s | 13 of 21 turns | **7 of 21 turns had no spoken reply at all** |
| A separate text model corrects the transcript | not delayed; the text after 1.5 s | 21 of 21 | Invented words ("엘레 사이트로" → "아메리카노 아이스로", "이요." → a whole order) |

- About 0.2–0.4 s slower when the model writes the text; but it does so only half of the time.
- With this voice the model itself took "엘레사이트" for 아인슈페너 in 4 of 6 sessions: a
  subtitle with the model's understanding would at least show the customer that it misheard.
- The transcription wrote "아이스요" as "I see", "아이세요" or "아이셀"; these are now aliases of
  ICE, so the required-option check accepts them.

Decision: keep the raw transcription for now.

## Still to check by a person

- **Real voice recognition and barge-in**: `uv run python scripts/live_check.py mic
  --start-sensitivity high --prefix-ms 300`. Talk through the earbuds/handset; Ctrl+C ends.
  Each turn prints what was heard, said and called, with the latency.
- **Voice**: listen to `recordings/live_check/voice-*.wav` (Kore, Aoede, Leda, Zephyr, Puck,
  Charon, Sulafat, Achernar) and pick one (`live.voice` in `configs/settings.yaml`).
- **Free-tier Live quotas**: [AI Studio rate limits](https://aistudio.google.com/rate-limit).
