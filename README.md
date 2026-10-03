# voice-kiosk

A café kiosk that customers operate **with their voice only**, through a telephone-style handset.
The customer lifts the handset, an AI assistant greets them in Korean, takes the order and drives
a clean, animated display. There are no touch buttons.

This is a **demo of an idea**, not a product: payment is simulated.

| | | |
|---|---|---|
| ![Start](docs/screenshots/start.jpg) | ![Recommended items](docs/screenshots/recommended.jpg) | ![An item and its required choices](docs/screenshots/item.jpg) |
| ![Allergy-safe items](docs/screenshots/allergy.jpg) | ![Card terminal](docs/screenshots/payment.jpg) | ![Order number](docs/screenshots/done.jpg) |

- [Try the kiosk (no programming needed)](#try-the-kiosk-no-programming-needed)
- [For developers](#for-developers)

## Try the kiosk (no programming needed)

You need:

- A **Windows 10 or 11** PC with an internet connection. Microsoft Edge is already on it.
- A **Google account**, for your own free Gemini API key (the step below shows how).
- Something to talk into: a headset, earbuds with a microphone, or the PC's microphone with
  earphones. Open laptop speakers also work, but the assistant may hear itself (see
  [Problems](#problems)).

### 1. Download

1. Open the [latest release page](https://github.com/jhj1012/voice-kiosk/releases/latest).
2. Under **Assets**, click **`voice-kiosk.zip`**. Edge saves it in your **Downloads** folder
   (다운로드). If Edge asks whether to keep the file, choose **Keep** (유지).

Do not use the green **Code → Download ZIP** button on the main page: that zip does not contain
the built display.

### 2. Unblock and unzip

Windows is careful with files from the internet; unblocking the zip first saves warnings later.

1. Open the **Downloads** folder, **right-click** `voice-kiosk.zip` and choose **Properties**
   (속성).
2. At the bottom of the **General** (일반) tab, tick **Unblock** (차단 해제) and click **OK**
   (확인). If there is no such box, skip this.
3. Right-click `voice-kiosk.zip` again and choose **Extract All…** (압축 풀기…). Pick a folder
   you will find again (e.g. **Documents** / 문서) and click **Extract** (압축 풀기).
4. Open the new **`voice-kiosk`** folder. You should see `Start Kiosk.bat` in it.

### 3. Start the kiosk

1. **Double-click `Start Kiosk.bat`.** If Windows asks whether to run it, choose **Run** (실행);
   if a blue "Windows protected your PC" (Windows의 PC 보호) box appears, click **More info**
   (추가 정보) and then **Run anyway** (실행).
2. A **black window** opens. The first time, it installs what the kiosk needs; this takes one or
   two minutes. Leave the black window open: **closing it turns the kiosk off**.
3. The kiosk then opens in its own window.

### 4. Enter your API key (only the first time)

The kiosk asks for a **Gemini API key**: it lets the kiosk talk to Google's AI with your account.

![The API key form](docs/screenshots/api-key.jpg)

1. Click **Google AI Studio 열기** in the kiosk window and sign in with your Google account.
2. Click **Create API key** (API 키 만들기). If it asks for a project, pick the suggested one.
3. Click the **copy** button next to the new key.
4. Back in the kiosk window, click the box, paste with **Ctrl+V** and click **저장**.
5. When it says **저장했어요**, you are done. The key is saved in the `voice-kiosk` folder (in a
   file named `.env`) and works from now on.

Keep your key to yourself: anyone with it can use your Gemini account. On the free plan Google
may use the conversations to improve its products, so do not say anything private to the kiosk.

### 5. Talk to it

| Do | How |
|---|---|
| Lift the handset | Click the kiosk window once, then press **Space** |
| Order | Just talk, e.g. "메뉴 뭐 있어요?", "아이스 아메리카노 라지로 한 잔 주세요", "결제할게요". You can interrupt the assistant while it speaks. |
| Hang up | Press **Space** again (this also clears the order) |
| Type instead of talking | Press **F2**, type in the box and press **Enter**. **F2** again hides it. |
| Change the API key | Press **F2**, then click **API 키 바꾸기** |

Payment is pretend: after the assistant reads the order back, a card terminal appears, and a
few seconds later you get an order number.

### 6. Turn it off

Close the kiosk window, then close the **black window**.

**Full screen** (for the real kiosk screen): double-click **`Start Kiosk (full screen).bat`**
instead. Press **Alt+F4** to leave full screen, then close the black window.

### Microphone and speaker

The kiosk uses Windows' **default** microphone and speaker. To use a headset or handset, plug it
in, then open **Settings → System → Sound** (설정 → 시스템 → 소리) and choose it under
**Output** (출력) and **Input** (입력). Restart the kiosk afterwards (close the black window and
double-click `Start Kiosk.bat` again).

### A new version

Download the new `voice-kiosk.zip` and unzip it to a **new** folder (steps 1–2). To keep your
API key, copy the file **`.env`** from the old `voice-kiosk` folder into the new one, or simply
enter the key again.

### Problems

| What you see | What to do |
|---|---|
| The black window flashes and disappears, or "uv를 설치하지 못했어요" | Check the internet connection and start again. Did you unblock the zip (step 2)? |
| "화면 파일(frontend\dist)이 없어요" | You downloaded the wrong zip: use `voice-kiosk.zip` from the release page (step 1). |
| The key form says "Google에 연결할 수 없어요" | Check the internet connection and click 저장 again. |
| "Google이 이 키를 받아 주지 않았어요" | Copy the key again (the whole key), or create a new one. |
| "지금은 연결할 수 없어요" when you lift the handset | Internet, or Google is busy: wait a moment and try again. The free plan also has a daily limit. |
| The assistant does not hear you | Choose the right microphone in Windows (see above) and restart the kiosk. |
| The assistant stops in the middle of its sentence | It hears itself through the speakers: use earphones or a headset. |
| Nothing happens when you press Space | Click inside the kiosk window first. |

Still stuck? Send the newest file from the `logs` folder in `voice-kiosk` to the team (it holds the
conversation as text; no audio and no API key).

## For developers

- Conversation: the [Gemini Live API](https://ai.google.dev/gemini-api/docs/live) (one streaming
  session per customer: audio in, audio out, interruptions, transcripts, function calls).
- Backend: Python 3.12 (`uv`), FastAPI. It owns the order, validates every action of the model
  and enforces the safety rules (payment, discarding the order) in code.
- Display: Svelte + TypeScript, full-screen in Edge kiosk mode. It only renders what the backend
  pushes over a WebSocket.

Built in eight milestones, all done (see [docs/architecture.md](docs/architecture.md#milestones)
and the [Live API check](docs/live-check.md)).

### Quick start

Needs [uv](https://docs.astral.sh/uv/), [Node.js](https://nodejs.org/) 24 and git; details in
[docs/setup.md](docs/setup.md).

```bash
git clone https://github.com/jhj1012/voice-kiosk.git
cd voice-kiosk
uv sync
npm --prefix frontend ci
npm --prefix frontend run build
uv run python -m kiosk --open   # or double-click Start Kiosk.bat
```

The API key goes in `.env` (`GEMINI_API_KEY=...`, see `.env.example`) or into the form the
display shows. Audio devices: `configs/settings.local.yaml`, see
[docs/setup.md](docs/setup.md#the-handsets-audio).

### Before a demo

A whole order, spoken by the Windows Korean voice into the kiosk, through the real Live API;
PASS/FAIL per step, reply times and screenshots (in `recordings/voice_demo/`):

```bash
uv run python scripts/voice_demo.py            # --listen: hear the assistant on the speakers
```

### Publishing a release

Pushing a tag builds the display and publishes `voice-kiosk.zip` on the Releases page
(`.github/workflows/release.yml`):

```bash
git tag v0.1.0
git push origin v0.1.0
```

### Repository layout

| Path | What |
|---|---|
| `kiosk/domain/` | Menu, order and kiosk flow. Pure Python, fully tested. |
| `kiosk/assistant/` | The Live session, instructions, function declarations, safety rules. |
| `kiosk/voice/` | Audio devices (handset mic and earpiece) and the hook switch. |
| `kiosk/server/` | Wiring, the WebSocket server for the display and the API key form. |
| `frontend/` | The display (Svelte). |
| `data/` | `menu.yaml`, `cafe.yaml` and `images/<item_id>.png`: edit these to change the menu. |
| `configs/` | `settings.yaml`; personal overrides go in git-ignored `settings.local.yaml`. |
| `scripts/` | `start.ps1` (behind `Start Kiosk.bat`), `voice_demo.py`, `live_check.py`, `make_demo_events.py`. |
| `docs/` | [Architecture](docs/architecture.md), [decisions](docs/decisions.md), [setup](docs/setup.md), [Live API check](docs/live-check.md). |

### Checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run lint-imports
uv run pytest
npm --prefix frontend run lint
npm --prefix frontend run check
npm --prefix frontend test
npm --prefix frontend run build
```

### Contributing

Branch → pull request → review. See [CONTRIBUTING.md](CONTRIBUTING.md).
This repository is **public**: never commit API keys, `.env`, `*.local.yaml`, recordings or logs.
