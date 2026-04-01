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
# Locate the closing `>` of an opening <speak ...> tag for preamble injection.
_SPEAK_OPEN_RE = re.compile(r'(<speak\b[^>]*>)', re.IGNORECASE)


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

    Synthesises text to MP3 audio via dashscope.audio.tts_v3.SpeechSynthesizer.
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
            from dashscope.audio.tts_v3 import SpeechSynthesizer
        except ImportError:
            logger.error("dashscope not installed. Run: pip install dashscope")
            return False

        if self.config.preamble:
            if _SPEAK_OPEN_RE.search(text):
                # SSML: inject preamble immediately after the opening <speak ...> tag
                tts_text = _SPEAK_OPEN_RE.sub(lambda m: m.group(1) + self.config.preamble, text, count=1)
            else:
                tts_text = self.config.preamble + text
        else:
            tts_text = text
        try:
            result = await asyncio.to_thread(
                SpeechSynthesizer.call,
                model=self.config.model,
                text=tts_text,
                voice=self.config.voice,
                format=self.config.format,
                api_key=self.api_key,
            )
            audio_data = result.get_audio_data()
            if not audio_data:
                logger.warning("TTS: CosyVoice returned empty audio for tts_text length={}", len(tts_text))
                return False
            Path(output_path).write_bytes(audio_data)
            logger.debug("TTS: synthesised {} bytes → {}", len(audio_data), output_path)
            return True
        except Exception as e:
            logger.warning("TTS synthesis failed: {}", e)
            return False
