"""The google-genai adapter's pure parts: the connect config and the message -> event mapping."""

import asyncio

import pytest
from google.genai import errors, types

from kiosk.assistant.live import (
    AudioOut,
    FunctionCall,
    GoAway,
    InputText,
    Interrupted,
    OutputText,
    Resumable,
    SessionSetup,
    ToolCall,
    TurnComplete,
    check_api_key,
    connect_config,
    is_key_error,
    to_events,
)
from kiosk.config import LiveConfig

SETUP = SessionSetup(
    instructions="rules",
    tools=[{"name": "show_order", "description": "Show the order."}],
    vocabulary=["아메리카노", "라지"],
)


def test_connect_config_from_settings():
    config = connect_config(LiveConfig(voice="Sulafat"), SETUP)
    assert config.response_modalities == [types.Modality.AUDIO]
    assert config.system_instruction is not None
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Sulafat"
    assert config.speech_config.language_code == "ko-KR"
    assert config.input_audio_transcription.language_codes == ["ko-KR"]
    assert config.input_audio_transcription.custom_vocabulary == ["아메리카노", "라지"]
    assert config.output_audio_transcription.language_codes == ["ko-KR"]
    detection = config.realtime_input_config.automatic_activity_detection
    assert detection.start_of_speech_sensitivity == types.StartSensitivity.START_SENSITIVITY_HIGH
    assert detection.prefix_padding_ms == 300
    assert detection.silence_duration_ms is None
    assert config.session_resumption is not None and config.session_resumption.handle is None
    assert config.context_window_compression is not None
    assert config.tools[0].function_declarations[0].name == "show_order"


def test_connect_config_resumes_and_respects_empty_settings():
    setup = SessionSetup("rules", [], [], resume_handle="abc")
    config = connect_config(
        LiveConfig(voice="", start_sensitivity="", prefix_padding_ms=None, vocabulary=False), setup
    )
    assert config.session_resumption.handle == "abc"
    assert config.speech_config.voice_config is None
    assert config.realtime_input_config is None
    assert config.input_audio_transcription.custom_vocabulary is None


def message(**fields) -> types.LiveServerMessage:
    return types.LiveServerMessage.model_validate(fields)


def test_to_events_maps_content():
    events = to_events(
        message(
            server_content={
                "input_transcription": {"text": "아이스"},
                "output_transcription": {"text": "네"},
                "model_turn": {"parts": [{"inline_data": {"data": b"\x01\x02", "mime_type": "x"}}]},
                "turn_complete": True,
            }
        )
    )
    assert events == [InputText("아이스"), OutputText("네"), AudioOut(b"\x01\x02"), TurnComplete()]


def test_to_events_maps_control_messages():
    assert to_events(message(server_content={"interrupted": True})) == [Interrupted()]
    assert to_events(
        message(tool_call={"function_calls": [{"id": "1", "name": "show_order", "args": {}}]})
    ) == [ToolCall((FunctionCall("1", "show_order", {}),))]
    assert to_events(message(session_resumption_update={"resumable": True, "new_handle": "h"})) == [
        Resumable("h")
    ]
    assert to_events(message(session_resumption_update={"resumable": False})) == []
    assert to_events(message(go_away={"time_left": "10s"})) == [GoAway(10.0)]


BAD_KEY = errors.ClientError(
    400, {"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT"}}
)


class FakeModels:
    def __init__(self, error: Exception | None) -> None:
        self.error = error

    async def get(self, model: str) -> object:
        if self.error is not None:
            raise self.error
        return object()


class FakeClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.aio = type("Aio", (), {"models": FakeModels(error)})()


@pytest.mark.parametrize(
    ("error", "result"),
    [(None, "ok"), (BAD_KEY, "rejected"), (ConnectionError("no internet"), "offline")],
)
def test_check_api_key(error, result):
    checked = asyncio.run(check_api_key(LiveConfig(), "key", client=FakeClient(error)))
    assert checked == result


def test_key_errors():
    assert is_key_error(BAD_KEY)
    assert is_key_error(errors.ClientError(403, {"error": {"message": "permission denied"}}))
    assert not is_key_error(errors.ClientError(429, {"error": {"message": "quota"}}))
    assert not is_key_error(ConnectionError("API key"))
