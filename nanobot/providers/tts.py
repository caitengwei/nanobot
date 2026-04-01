"""TTS (text-to-speech) providers."""

import asyncio
import os
import re
from pathlib import Path

from loguru import logger

from nanobot.config.schema import TTSConfig

# Matches CosyVoice inline control tags:
#   <|tag|>value   e.g. <|speaking_rate|>slow, <|emotion|>happy, <|volume|>high
#   </|tag|>       closing variant e.g. </|strong|>
#   [marker]       paralinguistic e.g. [laughter], [breath]
_TTS_CONTROL_TAG_RE = re.compile(
    r"</??\|[^|>]+\|>(?:\s*[a-zA-Z][a-zA-Z_]*)?"  # <|tag|> or </|tag|> + optional ASCII value
    r"|\[[a-zA-Z][a-zA-Z_]*\]"                      # [marker] paralinguistic tags
)


def strip_tts_control_tags(text: str) -> str:
    """Remove CosyVoice control tags from text before sending as plain text."""
    return _TTS_CONTROL_TAG_RE.sub("", text).strip()


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

        tts_text = f"{self.config.preamble}{text}" if self.config.preamble else text
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
                logger.warning("TTS: CosyVoice returned empty audio for text length={}", len(text))
                return False
            Path(output_path).write_bytes(audio_data)
            logger.debug("TTS: synthesised {} bytes → {}", len(audio_data), output_path)
            return True
        except Exception as e:
            logger.warning("TTS synthesis failed: {}", e)
            return False
