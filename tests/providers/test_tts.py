"""Tests for CosyVoiceTTSProvider."""

from unittest.mock import MagicMock, patch

import pytest

from nanobot.config.schema import TTSConfig
from nanobot.providers.tts import CosyVoiceTTSProvider, strip_tts_control_tags


def _provider(api_key: str = "sk-test") -> CosyVoiceTTSProvider:
    return CosyVoiceTTSProvider(TTSConfig(api_key=api_key, voice="Asuka-Plus", model="cosyvoice-v3.5-plus"))


def _mock_tts_v2(audio_bytes: bytes | None = b"fake-mp3-bytes"):
    """Return (mock_module, mock_instance) for dashscope.audio.tts_v2."""
    mock_instance = MagicMock()
    mock_instance.call.return_value = audio_bytes
    mock_class = MagicMock(return_value=mock_instance)
    mock_module = MagicMock()
    mock_module.SpeechSynthesizer = mock_class
    mock_module.AudioFormat = MagicMock()
    mock_module.AudioFormat.MP3_16000HZ_MONO_128KBPS = MagicMock()
    return mock_module, mock_instance


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
    with patch.dict("sys.modules", {"dashscope": None, "dashscope.audio": None, "dashscope.audio.tts_v2": None}):
        result = await provider.synthesize("hello", tmp_path / "out.mp3")
    assert result is False


@pytest.mark.asyncio
async def test_cosyvoice_empty_audio_returns_false(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    provider = _provider()
    mock_tts_v2, _ = _mock_tts_v2(audio_bytes=None)
    mock_dashscope = MagicMock()
    with patch.dict("sys.modules", {
        "dashscope": mock_dashscope,
        "dashscope.audio": MagicMock(),
        "dashscope.audio.tts_v2": mock_tts_v2,
    }):
        result = await provider.synthesize("hello", tmp_path / "out.mp3")
    assert result is False


@pytest.mark.asyncio
async def test_cosyvoice_happy_path(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    provider = _provider()
    mock_tts_v2, _ = _mock_tts_v2(b"fake-mp3-bytes")
    mock_dashscope = MagicMock()
    out = tmp_path / "voice.mp3"
    with patch.dict("sys.modules", {
        "dashscope": mock_dashscope,
        "dashscope.audio": MagicMock(),
        "dashscope.audio.tts_v2": mock_tts_v2,
    }):
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
async def test_preamble_passed_as_instruction_to_synthesizer(tmp_path, monkeypatch):
    """synthesize() must pass preamble as instruction= kwarg to SpeechSynthesizer, not in call()."""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    preamble = "式波明日香，傲娇直率，情绪外放。"
    provider = CosyVoiceTTSProvider(
        TTSConfig(api_key="sk-test", voice="Asuka-Plus", model="cosyvoice-v3.5-plus",
                  preamble=preamble)
    )
    mock_tts_v2, mock_instance = _mock_tts_v2(b"fake")
    mock_dashscope = MagicMock()
    with patch.dict("sys.modules", {
        "dashscope": mock_dashscope,
        "dashscope.audio": MagicMock(),
        "dashscope.audio.tts_v2": mock_tts_v2,
    }):
        await provider.synthesize("你好", tmp_path / "out.mp3")

    # preamble goes to instruction= on the constructor, not in call()
    init_kwargs = mock_tts_v2.SpeechSynthesizer.call_args[1]
    assert init_kwargs.get("instruction") == preamble
    # synthesizer.call() receives only the original text, no preamble prepended
    assert mock_instance.call.call_args[0][0] == "你好"


@pytest.mark.asyncio
async def test_preamble_instruction_not_in_call_text_for_ssml(tmp_path, monkeypatch):
    """When text is SSML, preamble still goes to instruction=, not into the SSML string."""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    preamble = "式波明日香，傲娇直率，情绪外放。"
    provider = CosyVoiceTTSProvider(
        TTSConfig(api_key="sk-test", voice="Asuka-Plus", model="cosyvoice-v3.5-plus",
                  preamble=preamble)
    )
    mock_tts_v2, mock_instance = _mock_tts_v2(b"fake")
    mock_dashscope = MagicMock()
    ssml = '<speak rate="0.8">你好世界</speak>'
    with patch.dict("sys.modules", {
        "dashscope": mock_dashscope,
        "dashscope.audio": MagicMock(),
        "dashscope.audio.tts_v2": mock_tts_v2,
    }):
        await provider.synthesize(ssml, tmp_path / "out.mp3")

    init_kwargs = mock_tts_v2.SpeechSynthesizer.call_args[1]
    assert init_kwargs.get("instruction") == preamble
    # SSML passed unchanged to call()
    assert mock_instance.call.call_args[0][0] == ssml


@pytest.mark.asyncio
async def test_cosyvoice_api_exception_returns_false(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    provider = _provider()
    mock_tts_v2, mock_instance = _mock_tts_v2()
    mock_instance.call.side_effect = RuntimeError("API error")
    mock_dashscope = MagicMock()
    with patch.dict("sys.modules", {
        "dashscope": mock_dashscope,
        "dashscope.audio": MagicMock(),
        "dashscope.audio.tts_v2": mock_tts_v2,
    }):
        result = await provider.synthesize("hello", tmp_path / "out.mp3")
    assert result is False
