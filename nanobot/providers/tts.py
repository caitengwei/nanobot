"""TTS (text-to-speech) providers."""

import asyncio
import os
import re
from pathlib import Path

from loguru import logger

from nanobot.config.schema import TTSConfig

# CosyVoice SSML void tags: these produce no spoken text — remove entirely.
_SSML_VOID_RE = re.compile(r'<(?:break|soundEvent)\b[^>]*/>', re.IGNORECASE)
# CosyVoice SSML wrapping tags: strip tags but keep inner text.
_SSML_WRAP_RE = re.compile(r'</?(?:speak|sub|phoneme|say-as)\b[^>]*>', re.IGNORECASE)

# Map config format strings to dashscope AudioFormat enum names.
# AudioFormat members follow the pattern <FORMAT>_<RATE>HZ_MONO_<BITRATE>.
_FORMAT_TO_AUDIO_FORMAT = {
    "mp3": "MP3_16000HZ_MONO_128KBPS",
    "wav": "WAV_16000HZ_MONO_16BIT",
    "pcm": "PCM_16000HZ_MONO_16BIT",
}
_DEFAULT_AUDIO_FORMAT = "MP3_16000HZ_MONO_128KBPS"


def strip_tts_control_tags(text: str) -> str:
    """Remove CosyVoice SSML markup from text before sending as plain text.

    Void tags (break, soundEvent) are removed entirely.
    Wrapping tags (speak, phoneme, sub, say-as) are removed but their content is kept.
    """
    text = _SSML_VOID_RE.sub("", text)
    text = _SSML_WRAP_RE.sub("", text)
    return text.strip()


class CosyVoiceTTSProvider:
    """
    TTS provider using Alibaba Cloud Bailian CosyVoice.

    Synthesises text to audio via dashscope.audio.tts_v2.SpeechSynthesizer.
    Requires: pip install dashscope  (included in qwen3-asr extra)
    API key: https://dashscope.console.aliyun.com/
    """

    def __init__(self, config: TTSConfig):
        self.config = config
        self.api_key = config.api_key or os.environ.get("DASHSCOPE_API_KEY", "")

    async def synthesize(self, text: str, output_path: Path) -> bool:
        """
        Synthesise text to audio and write to output_path.

        Returns True on success, False on any failure (non-fatal).
        """
        if not self.api_key:
            logger.warning("TTS: no api_key configured, skipping voice synthesis")
            return False

        try:
            import dashscope
            from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer
        except ImportError:
            logger.error("dashscope not installed. Run: pip install dashscope")
            return False

        fmt = (self.config.format or "").strip().lstrip(".").lower() or "mp3"
        audio_format_name = _FORMAT_TO_AUDIO_FORMAT.get(fmt, _DEFAULT_AUDIO_FORMAT)
        audio_format = getattr(AudioFormat, audio_format_name, AudioFormat.MP3_16000HZ_MONO_128KBPS)

        try:
            dashscope.api_key = self.api_key
            synthesizer = SpeechSynthesizer(
                model=self.config.model,
                voice=self.config.voice,
                format=audio_format,
                instruction=self.config.preamble or None,
                callback=None,
            )
            audio_data: bytes = await asyncio.to_thread(synthesizer.call, text)
            if not audio_data:
                logger.warning("TTS: CosyVoice returned empty audio for text length={}", len(text))
                return False
            Path(output_path).write_bytes(audio_data)
            logger.debug("TTS: synthesised {} bytes → {}", len(audio_data), output_path)
            return True
        except Exception as e:
            logger.warning("TTS synthesis failed: {}", e)
            return False
