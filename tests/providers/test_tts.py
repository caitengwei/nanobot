"""Tests for CosyVoiceTTSProvider."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nanobot.config.schema import TTSConfig
from nanobot.providers.tts import CosyVoiceTTSProvider, strip_tts_control_tags


def _provider(api_key: str = "sk-test") -> CosyVoiceTTSProvider:
    return CosyVoiceTTSProvider(TTSConfig(api_key=api_key, voice="Asuka-Plus", model="cosyvoice-v2-plus"))


@pytest.mark.asyncio
async def test_cosyvoice_no_api_key_returns_false(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    provider = CosyVoiceTTSProvider(TTSConfig(api_key=""))
    result = await provider.synthesize("hello", tmp_path / "out.mp3")
    assert result is False


@pytest.mark.asyncio
async def test_cosyvoice_import_error_returns_false(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    provider = _provider()
    with patch.dict("sys.modules", {"dashscope": None, "dashscope.audio": None, "dashscope.audio.tts_v3": None}):
        result = await provider.synthesize("hello", tmp_path / "out.mp3")
    assert result is False


@pytest.mark.asyncio
async def test_cosyvoice_empty_audio_returns_false(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    provider = _provider()
    mock_result = MagicMock()
    mock_result.get_audio_data.return_value = None
    mock_synthesizer = MagicMock()
    mock_synthesizer.call.return_value = mock_result
    with patch.dict("sys.modules", {"dashscope": MagicMock(), "dashscope.audio": MagicMock(), "dashscope.audio.tts_v3": MagicMock(SpeechSynthesizer=mock_synthesizer)}):
        result = await provider.synthesize("hello", tmp_path / "out.mp3")
    assert result is False


@pytest.mark.asyncio
async def test_cosyvoice_happy_path(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    provider = _provider()
    mock_result = MagicMock()
    mock_result.get_audio_data.return_value = b"fake-mp3-bytes"
    mock_synthesizer = MagicMock()
    mock_synthesizer.call.return_value = mock_result
    out = tmp_path / "voice.mp3"
    with patch.dict("sys.modules", {"dashscope": MagicMock(), "dashscope.audio": MagicMock(), "dashscope.audio.tts_v3": MagicMock(SpeechSynthesizer=mock_synthesizer)}):
        result = await provider.synthesize("你好，世界", out)
    assert result is True
    assert out.exists()
    assert out.read_bytes() == b"fake-mp3-bytes"


def test_strip_tts_control_tags_removes_cosyvoice_ssml():
    # speak wrapper removed, content preserved
    assert strip_tts_control_tags('<speak>你好</speak>') == "你好"
    # break is a void tag — removed entirely (no content to keep)
    assert strip_tts_control_tags('你好<break time="500ms"/>今天') == "你好今天"
    # soundEvent is a void tag — removed entirely
    assert strip_tts_control_tags('开始<soundEvent src="url"/>结束') == "开始结束"
    # phoneme — inner text kept
    assert strip_tts_control_tags('<phoneme alphabet="py" ph="dian3">典</phoneme>当行') == "典当行"
    # sub — inner text kept (alias discarded)
    assert strip_tts_control_tags('<sub alias="网络协议">W3C</sub>') == "W3C"
    # say-as — inner text kept
    assert strip_tts_control_tags('<say-as interpret-as="telephone">12345</say-as>') == "12345"
    # full SSML example
    assert strip_tts_control_tags('<speak rate="0.8">你好<break time="500ms"/>世界</speak>') == "你好世界"


def test_strip_tts_control_tags_preserves_normal_text():
    assert strip_tts_control_tags("今天天气很好") == "今天天气很好"
    assert strip_tts_control_tags("") == ""
    assert strip_tts_control_tags("  空格  ") == "空格"


@pytest.mark.asyncio
async def test_preamble_prepended_to_synthesize_text(tmp_path, monkeypatch):
    """synthesize() must prepend preamble to the text passed to SpeechSynthesizer."""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    provider = CosyVoiceTTSProvider(
        TTSConfig(api_key="sk-test", voice="Asuka-Plus", model="cosyvoice-v3.5-plus",
                  preamble="式波明日香，傲娇直率，情绪外放。")
    )
    mock_result = MagicMock()
    mock_result.get_audio_data.return_value = b"fake"
    mock_synthesizer = MagicMock()
    mock_synthesizer.call.return_value = mock_result

    with patch.dict("sys.modules", {
        "dashscope": MagicMock(), "dashscope.audio": MagicMock(),
        "dashscope.audio.tts_v3": MagicMock(SpeechSynthesizer=mock_synthesizer),
    }):
        await provider.synthesize("你好", tmp_path / "out.mp3")

    called_text = mock_synthesizer.call.call_args.kwargs["text"]
    assert "式波明日香，傲娇直率，情绪外放。" in called_text
    assert "你好" in called_text


@pytest.mark.asyncio
async def test_preamble_injected_inside_speak_tag_for_ssml(tmp_path, monkeypatch):
    """When text is SSML, preamble must go inside <speak>, not before it."""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    provider = CosyVoiceTTSProvider(
        TTSConfig(api_key="sk-test", voice="Asuka-Plus", model="cosyvoice-v3.5-plus",
                  preamble="式波明日香，傲娇直率，情绪外放。")
    )
    mock_result = MagicMock()
    mock_result.get_audio_data.return_value = b"fake"
    mock_synthesizer = MagicMock()
    mock_synthesizer.call.return_value = mock_result

    ssml = '<speak rate="0.8">你好世界</speak>'
    with patch.dict("sys.modules", {
        "dashscope": MagicMock(), "dashscope.audio": MagicMock(),
        "dashscope.audio.tts_v3": MagicMock(SpeechSynthesizer=mock_synthesizer),
    }):
        await provider.synthesize(ssml, tmp_path / "out.mp3")

    called_text = mock_synthesizer.call.call_args.kwargs["text"]
    # preamble must be inside <speak>, not prepended outside
    assert called_text.startswith("<speak")
    assert "式波明日香，傲娇直率，情绪外放。" in called_text
    assert "你好世界" in called_text


@pytest.mark.asyncio
async def test_cosyvoice_api_exception_returns_false(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    provider = _provider()
    mock_synthesizer = MagicMock()
    mock_synthesizer.call.side_effect = RuntimeError("API error")
    with patch.dict("sys.modules", {"dashscope": MagicMock(), "dashscope.audio": MagicMock(), "dashscope.audio.tts_v3": MagicMock(SpeechSynthesizer=mock_synthesizer)}):
        result = await provider.synthesize("hello", tmp_path / "out.mp3")
    assert result is False
