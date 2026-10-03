"""The Live API connection behind a small interface, so the session can be tested with a fake.

`LiveConnector.connect` opens one streaming connection; the session sends audio, text and
function results, and reads `ServerEvent`s. `GeminiConnector` implements it with google-genai;
`connect_config` and `to_events` are pure and tested without a network.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from google import genai
from google.genai import types

from kiosk.config import LiveConfig

log = logging.getLogger(__name__)

IN_MIME = "audio/pcm;rate=16000"


# --- events from the server --------------------------------------------------------------------


@dataclass(frozen=True)
class AudioOut:
    data: bytes  # 24 kHz 16-bit mono PCM


@dataclass(frozen=True)
class InputText:
    """A piece of the transcription of what the customer said."""

    text: str


@dataclass(frozen=True)
class OutputText:
    """A piece of the transcription of what the assistant says."""

    text: str


@dataclass(frozen=True)
class FunctionCall:
    id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    calls: tuple[FunctionCall, ...]


@dataclass(frozen=True)
class Interrupted:
    """The customer started talking: the assistant's audio must stop at once."""


@dataclass(frozen=True)
class TurnComplete:
    pass


@dataclass(frozen=True)
class GoAway:
    """The server will close the connection soon."""

    time_left_s: float | None = None


@dataclass(frozen=True)
class Resumable:
    """A handle to resume this conversation on a new connection."""

    handle: str


ServerEvent = (
    AudioOut | InputText | OutputText | ToolCall | Interrupted | TurnComplete | GoAway | Resumable
)


# --- the interface -----------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionSetup:
    instructions: str
    tools: list[dict[str, Any]]
    vocabulary: Sequence[str] = ()  # words to bias the transcription towards
    resume_handle: str | None = None


class LiveConnection(Protocol):
    async def send_audio(self, pcm: bytes) -> None: ...

    async def send_text(self, text: str) -> None: ...

    async def send_results(self, results: Sequence[tuple[FunctionCall, dict[str, Any]]]) -> None:
        """Answer function calls with their results."""
        ...

    def events(self) -> AsyncIterator[ServerEvent]:
        """Everything the server sends; ends when the connection closes."""
        ...

    async def close(self) -> None: ...


class LiveConnector(Protocol):
    async def connect(self, setup: SessionSetup) -> LiveConnection: ...


# --- google-genai ------------------------------------------------------------------------------


def connect_config(config: LiveConfig, setup: SessionSetup) -> types.LiveConnectConfig:
    speech: dict[str, Any] = {}
    if config.voice:
        speech["voice_config"] = {"prebuilt_voice_config": {"voice_name": config.voice}}
    if config.language:
        speech["language_code"] = config.language
    transcription: dict[str, Any] = {}
    if config.language:
        transcription["language_codes"] = [config.language]
    if config.vocabulary and setup.vocabulary:
        transcription["custom_vocabulary"] = list(setup.vocabulary)
    detection: dict[str, Any] = {}
    if config.start_sensitivity:
        detection["start_of_speech_sensitivity"] = (
            f"START_SENSITIVITY_{config.start_sensitivity.upper()}"
        )
    if config.end_sensitivity:
        detection["end_of_speech_sensitivity"] = f"END_SENSITIVITY_{config.end_sensitivity.upper()}"
    if config.prefix_padding_ms is not None:
        detection["prefix_padding_ms"] = config.prefix_padding_ms
    if config.silence_duration_ms is not None:
        detection["silence_duration_ms"] = config.silence_duration_ms
    values: dict[str, Any] = {
        "response_modalities": ["AUDIO"],
        "system_instruction": setup.instructions,
        "tools": [{"function_declarations": setup.tools}],
        "input_audio_transcription": transcription,
        "output_audio_transcription": (
            {"language_codes": [config.language]} if config.language else {}
        ),
        "session_resumption": {"handle": setup.resume_handle} if setup.resume_handle else {},
        "context_window_compression": {"sliding_window": {}},
    }
    if speech:
        values["speech_config"] = speech
    if detection:
        values["realtime_input_config"] = {"automatic_activity_detection": detection}
    return types.LiveConnectConfig.model_validate(values)


def to_events(message: types.LiveServerMessage) -> list[ServerEvent]:
    """Our events for one server message, in a sensible order."""
    events: list[ServerEvent] = []
    update = message.session_resumption_update
    if update is not None and update.resumable and update.new_handle:
        events.append(Resumable(update.new_handle))
    content = message.server_content
    if content is not None:
        if content.input_transcription is not None and content.input_transcription.text:
            events.append(InputText(content.input_transcription.text))
        if content.interrupted:
            events.append(Interrupted())
        if content.output_transcription is not None and content.output_transcription.text:
            events.append(OutputText(content.output_transcription.text))
        if content.model_turn is not None:
            for part in content.model_turn.parts or []:
                if part.inline_data is not None and part.inline_data.data:
                    events.append(AudioOut(part.inline_data.data))
    if message.tool_call is not None and message.tool_call.function_calls:
        calls = tuple(
            FunctionCall(id=c.id or "", name=c.name or "", args=dict(c.args or {}))
            for c in message.tool_call.function_calls
        )
        events.append(ToolCall(calls))
    if content is not None and content.turn_complete:
        events.append(TurnComplete())
    if message.go_away is not None:
        events.append(GoAway(_seconds(message.go_away.time_left)))
    return events


def _seconds(value: Any) -> float | None:
    if value is None:
        return None
    if hasattr(value, "total_seconds"):
        return float(value.total_seconds())
    with contextlib.suppress(TypeError, ValueError):
        return float(str(value).rstrip("s"))
    return None


class GeminiConnection:
    def __init__(self, context: Any, session: Any) -> None:
        self._context = context  # the SDK's async context manager, closed in close()
        self._session = session

    async def send_audio(self, pcm: bytes) -> None:
        await self._session.send_realtime_input(audio=types.Blob(data=pcm, mime_type=IN_MIME))

    async def send_text(self, text: str) -> None:
        await self._session.send_realtime_input(text=text)

    async def send_results(self, results: Sequence[tuple[FunctionCall, dict[str, Any]]]) -> None:
        responses = [
            types.FunctionResponse(id=call.id, name=call.name, response=result)
            for call, result in results
        ]
        await self._session.send_tool_response(function_responses=responses)

    async def events(self) -> AsyncIterator[ServerEvent]:
        # The SDK's receive() stops after each turn; an empty round means the socket closed.
        while True:
            received = False
            async for message in self._session.receive():
                received = True
                for event in to_events(message):
                    yield event
            if not received:
                return

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self._context.__aexit__(None, None, None)


class GeminiConnector:
    def __init__(self, config: LiveConfig, api_key: str, client: Any = None) -> None:
        self.config = config
        self._client = client or genai.Client(api_key=api_key)

    async def connect(self, setup: SessionSetup) -> GeminiConnection:
        context = self._client.aio.live.connect(
            model=self.config.model, config=connect_config(self.config, setup)
        )
        session = await context.__aenter__()
        log.info("Live session connected (%s)", self.config.model)
        return GeminiConnection(context, session)
