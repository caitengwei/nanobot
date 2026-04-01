"""Tests for WeChat TTS voice message integration."""

import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.weixin import WeixinChannel, WeixinConfig
from nanobot.config.schema import TTSConfig


def _make_channel(tts_api_key: str = "") -> WeixinChannel:
    bus = MessageBus()
    return WeixinChannel(
        WeixinConfig(
            enabled=True,
            allow_from=["*"],
            state_dir=tempfile.mkdtemp(prefix="nanobot-weixin-tts-test-"),
            tts=TTSConfig(api_key=tts_api_key, voice="Asuka-Plus", model="cosyvoice-v3.5-plus"),
        ),
        bus,
    )


def test_wants_voice_triggers_on_keywords():
    ch = _make_channel()
    assert ch._wants_voice("你说，今天天气怎么样") is True
    assert ch._wants_voice("你来说一下市场分析") is True
    assert ch._wants_voice("说给我听，关于这个问题") is True
    assert ch._wants_voice("用语音回答我") is True
    assert ch._wants_voice("语音回复") is True


def test_wants_voice_no_trigger_on_normal_text():
    ch = _make_channel()
    assert ch._wants_voice("帮我分析一下市场") is False
    assert ch._wants_voice("今天天气怎么样") is False
    assert ch._wants_voice("你好") is False
    assert ch._wants_voice("") is False


def test_voice_sessions_initialised_empty():
    ch = _make_channel()
    assert ch._voice_sessions == {}


@pytest.mark.asyncio
async def test_inbound_voice_trigger_sets_session_flag():
    """_process_message() must set _voice_sessions when content matches trigger."""
    ch = _make_channel()
    ch._token = "tok"

    await ch._process_message({
        "message_type": 1,
        "message_id": "m-voice-1",
        "from_user_id": "wx-user",
        "context_token": "ctx-1",
        "item_list": [
            {"type": 1, "text_item": {"text": "你说，帮我分析一下"}},
        ],
    })

    assert ch._voice_sessions.get("wx-user") is True


@pytest.mark.asyncio
async def test_send_calls_tts_and_sends_voice_when_session_flagged(tmp_path, monkeypatch):
    """When _voice_sessions is set, send() calls TTS and sends the MP3."""
    ch = _make_channel(tts_api_key="sk-test")
    ch._token = "tok"
    ch._context_tokens = {"wx-user": "ctx-1"}
    ch._voice_sessions["wx-user"] = True

    async def fake_synthesize(text: str, output_path) -> bool:
        from pathlib import Path
        Path(output_path).write_bytes(b"fake-mp3")
        return True

    ch._tts_provider.synthesize = fake_synthesize  # type: ignore

    sent_media = []
    sent_text = []

    async def fake_send_media(to, path, ctx):
        sent_media.append(str(path))

    async def fake_send_text(to, text, ctx):
        sent_text.append(text)

    ch._send_media_file = fake_send_media  # type: ignore
    ch._send_text = fake_send_text  # type: ignore
    ch._client = MagicMock()

    msg = OutboundMessage(channel="weixin", chat_id="wx-user", content="这是回复内容")
    await ch.send(msg)

    assert len(sent_media) == 1
    assert sent_media[0].endswith(".mp3")
    assert sent_text == ["这是回复内容"]
    assert "wx-user" not in ch._voice_sessions


@pytest.mark.asyncio
async def test_send_text_still_sent_when_tts_fails(monkeypatch):
    """If TTS synthesis fails, text is still sent normally."""
    ch = _make_channel(tts_api_key="sk-test")
    ch._token = "tok"
    ch._context_tokens = {"wx-user": "ctx-1"}
    ch._voice_sessions["wx-user"] = True
    ch._client = MagicMock()

    async def failing_synthesize(text, output_path) -> bool:
        return False

    ch._tts_provider.synthesize = failing_synthesize  # type: ignore

    sent_text = []

    async def fake_send_text(to, text, ctx):
        sent_text.append(text)

    ch._send_media_file = AsyncMock()
    ch._send_text = fake_send_text  # type: ignore

    msg = OutboundMessage(channel="weixin", chat_id="wx-user", content="回复")
    await ch.send(msg)

    assert sent_text == ["回复"]
    ch._send_media_file.assert_not_called()


@pytest.mark.asyncio
async def test_text_stripped_of_control_tags_when_voice_triggered():
    """SSML tags stripped from text only when voice was triggered."""
    ch = _make_channel(tts_api_key="sk-test")
    ch._token = "tok"
    ch._context_tokens = {"wx-user": "ctx-1"}
    ch._voice_sessions["wx-user"] = True
    ch._client = MagicMock()

    async def fake_synthesize(text, output_path) -> bool:
        from pathlib import Path
        Path(output_path).write_bytes(b"fake-mp3")
        return True

    ch._tts_provider.synthesize = fake_synthesize  # type: ignore

    sent_text = []

    async def fake_send_text(to, text, ctx):
        sent_text.append(text)

    ch._send_media_file = AsyncMock()
    ch._send_text = fake_send_text  # type: ignore

    raw = '<speak rate="0.8">你好<break time="500ms"/>，今天天气真好！</speak>'
    msg = OutboundMessage(channel="weixin", chat_id="wx-user", content=raw)
    await ch.send(msg)

    assert sent_text == ["你好，今天天气真好！"]


@pytest.mark.asyncio
async def test_ssml_always_stripped_even_without_voice_trigger():
    """SSML tags are always stripped from text, even without a voice trigger.

    This prevents raw XML from leaking to users when the LLM generates SSML
    in non-voice contexts.
    """
    ch = _make_channel(tts_api_key="sk-test")
    ch._token = "tok"
    ch._context_tokens = {"wx-user": "ctx-1"}
    ch._client = MagicMock()

    sent_text = []

    async def fake_send_text(to, text, ctx):
        sent_text.append(text)

    ch._send_media_file = AsyncMock()
    ch._send_text = fake_send_text  # type: ignore

    ssml = '<speak rate="0.9">你好世界</speak>'
    msg = OutboundMessage(channel="weixin", chat_id="wx-user", content=ssml)
    await ch.send(msg)

    assert sent_text == ["你好世界"]


@pytest.mark.asyncio
async def test_tts_receives_unstripped_ssml():
    """TTS synthesize() must receive the original SSML text including all tags."""
    ch = _make_channel(tts_api_key="sk-test")
    ch._token = "tok"
    ch._context_tokens = {"wx-user": "ctx-1"}
    ch._voice_sessions["wx-user"] = True
    ch._client = MagicMock()

    received_text: list[str] = []

    async def capturing_synthesize(text, output_path) -> bool:
        received_text.append(text)
        from pathlib import Path
        Path(output_path).write_bytes(b"fake-mp3")
        return True

    ch._tts_provider.synthesize = capturing_synthesize  # type: ignore
    ch._send_media_file = AsyncMock()
    ch._send_text = AsyncMock()

    raw = '<speak rate="0.8">你好<break time="500ms"/></speak>'
    msg = OutboundMessage(channel="weixin", chat_id="wx-user", content=raw)
    await ch.send(msg)

    assert len(received_text) == 1
    assert '<speak' in received_text[0]
    assert '<break' in received_text[0]


@pytest.mark.asyncio
async def test_send_skips_tts_when_no_provider():
    """If _tts_provider is None (no api_key), send() skips TTS silently."""
    ch = _make_channel(tts_api_key="")
    ch._token = "tok"
    ch._context_tokens = {"wx-user": "ctx-1"}
    ch._voice_sessions["wx-user"] = True
    ch._client = MagicMock()

    sent_media = []
    sent_text = []

    async def fake_send_media(to, path, ctx):  # pragma: no cover
        sent_media.append(path)

    async def fake_send_text(to, text, ctx):
        sent_text.append(text)

    ch._send_media_file = fake_send_media  # type: ignore
    ch._send_text = fake_send_text  # type: ignore

    msg = OutboundMessage(channel="weixin", chat_id="wx-user", content="回复")
    await ch.send(msg)

    assert sent_media == []
    assert sent_text == ["回复"]
