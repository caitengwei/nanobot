from __future__ import annotations

from pathlib import Path

import pytest

# Check optional Slack dependencies before running tests
try:
    import slack_sdk  # noqa: F401
except ImportError:
    pytest.skip("Slack dependencies not installed (slack-sdk)", allow_module_level=True)

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.slack import SlackChannel
from nanobot.channels.slack import SlackConfig


# ---------------------------------------------------------------------------
# Helpers for inbound socket-mode tests
# ---------------------------------------------------------------------------

class _FakeSocketClient:
    async def send_socket_mode_response(self, response) -> None:
        pass


class _FakeSocketRequest:
    def __init__(self, payload: dict):
        self.type = "events_api"
        self.envelope_id = "test-envelope"
        self.payload = payload


class _FakeHttpResponse:
    def __init__(self, content: bytes = b"fake-file-data"):
        self.content = content

    def raise_for_status(self) -> None:
        pass


class _FakeHttpClient:
    def __init__(self, content: bytes = b"fake-file-data"):
        self._content = content
        self.get_calls: list[dict] = []

    async def get(self, url: str, *, headers: dict | None = None, follow_redirects: bool = False):
        self.get_calls.append({"url": url, "headers": headers or {}})
        return _FakeHttpResponse(self._content)

    async def aclose(self) -> None:
        pass


def _make_channel(*, allow_from: list[str] | None = None, group_policy: str = "open") -> tuple[SlackChannel, MessageBus]:
    bus = MessageBus()
    cfg = SlackConfig(
        enabled=True,
        bot_token="xoxb-test-token",
        app_token="xoxapp-test",
        allow_from=allow_from or ["U123"],
        group_policy=group_policy,
    )
    ch = SlackChannel(cfg, bus)
    ch._web_client = _FakeAsyncWebClient()
    ch._bot_user_id = "UBOT"
    return ch, bus


class _FakeAsyncWebClient:
    def __init__(self) -> None:
        self.chat_post_calls: list[dict[str, object | None]] = []
        self.file_upload_calls: list[dict[str, object | None]] = []
        self.reactions_add_calls: list[dict[str, object | None]] = []
        self.reactions_remove_calls: list[dict[str, object | None]] = []

    async def chat_postMessage(
        self,
        *,
        channel: str,
        text: str,
        thread_ts: str | None = None,
    ) -> None:
        self.chat_post_calls.append(
            {
                "channel": channel,
                "text": text,
                "thread_ts": thread_ts,
            }
        )

    async def files_upload_v2(
        self,
        *,
        channel: str,
        file: str,
        thread_ts: str | None = None,
    ) -> None:
        self.file_upload_calls.append(
            {
                "channel": channel,
                "file": file,
                "thread_ts": thread_ts,
            }
        )

    async def reactions_add(
        self,
        *,
        channel: str,
        name: str,
        timestamp: str,
    ) -> None:
        self.reactions_add_calls.append(
            {
                "channel": channel,
                "name": name,
                "timestamp": timestamp,
            }
        )

    async def reactions_remove(
        self,
        *,
        channel: str,
        name: str,
        timestamp: str,
    ) -> None:
        self.reactions_remove_calls.append(
            {
                "channel": channel,
                "name": name,
                "timestamp": timestamp,
            }
        )


@pytest.mark.asyncio
async def test_send_uses_thread_for_channel_messages() -> None:
    channel = SlackChannel(SlackConfig(enabled=True), MessageBus())
    fake_web = _FakeAsyncWebClient()
    channel._web_client = fake_web

    await channel.send(
        OutboundMessage(
            channel="slack",
            chat_id="C123",
            content="hello",
            media=["/tmp/demo.txt"],
            metadata={"slack": {"thread_ts": "1700000000.000100", "channel_type": "channel"}},
        )
    )

    assert len(fake_web.chat_post_calls) == 1
    assert fake_web.chat_post_calls[0]["text"] == "hello\n"
    assert fake_web.chat_post_calls[0]["thread_ts"] == "1700000000.000100"
    assert len(fake_web.file_upload_calls) == 1
    assert fake_web.file_upload_calls[0]["thread_ts"] == "1700000000.000100"


@pytest.mark.asyncio
async def test_send_omits_thread_for_dm_messages() -> None:
    channel = SlackChannel(SlackConfig(enabled=True), MessageBus())
    fake_web = _FakeAsyncWebClient()
    channel._web_client = fake_web

    await channel.send(
        OutboundMessage(
            channel="slack",
            chat_id="D123",
            content="hello",
            media=["/tmp/demo.txt"],
            metadata={"slack": {"thread_ts": "1700000000.000100", "channel_type": "im"}},
        )
    )

    assert len(fake_web.chat_post_calls) == 1
    assert fake_web.chat_post_calls[0]["text"] == "hello\n"
    assert fake_web.chat_post_calls[0]["thread_ts"] is None
    assert len(fake_web.file_upload_calls) == 1
    assert fake_web.file_upload_calls[0]["thread_ts"] is None


@pytest.mark.asyncio
async def test_send_updates_reaction_when_final_response_sent() -> None:
    channel = SlackChannel(SlackConfig(enabled=True, react_emoji="eyes"), MessageBus())
    fake_web = _FakeAsyncWebClient()
    channel._web_client = fake_web

    await channel.send(
        OutboundMessage(
            channel="slack",
            chat_id="C123",
            content="done",
            metadata={
                "slack": {"event": {"ts": "1700000000.000100"}, "channel_type": "channel"},
            },
        )
    )

    assert fake_web.reactions_remove_calls == [
        {"channel": "C123", "name": "eyes", "timestamp": "1700000000.000100"}
    ]
    assert fake_web.reactions_add_calls == [
        {"channel": "C123", "name": "white_check_mark", "timestamp": "1700000000.000100"}
    ]


# ---------------------------------------------------------------------------
# Inbound file / image handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inbound_image_file_share_downloaded_and_forwarded(tmp_path, monkeypatch) -> None:
    """file_share event: image is downloaded with auth and forwarded as media."""
    monkeypatch.setattr("nanobot.channels.slack.get_media_dir", lambda _: tmp_path)

    ch, bus = _make_channel()
    fake_http = _FakeHttpClient(content=b"\x89PNG\r\n")
    ch._http = fake_http

    payload = {
        "event": {
            "type": "message",
            "subtype": "file_share",
            "user": "U123",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1700000000.000100",
            "text": "",
            "files": [
                {
                    "id": "FIMG1",
                    "name": "screenshot.png",
                    "mimetype": "image/png",
                    "url_private_download": "https://files.slack.com/files-pri/screenshot.png",
                }
            ],
        }
    }
    await ch._on_socket_request(_FakeSocketClient(), _FakeSocketRequest(payload))

    msg = bus.inbound.get_nowait()
    assert msg.media == [str(tmp_path / "FIMG1_screenshot.png")]
    assert len(fake_http.get_calls) == 1
    assert fake_http.get_calls[0]["headers"].get("Authorization") == "Bearer xoxb-test-token"


@pytest.mark.asyncio
async def test_inbound_image_in_regular_message_forwarded(tmp_path, monkeypatch) -> None:
    """Regular message (no subtype) with files array: image is downloaded and forwarded."""
    monkeypatch.setattr("nanobot.channels.slack.get_media_dir", lambda _: tmp_path)

    ch, bus = _make_channel()
    fake_http = _FakeHttpClient(content=b"jpeg-data")
    ch._http = fake_http

    payload = {
        "event": {
            "type": "message",
            "user": "U123",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1700000000.000200",
            "text": "看这张图",
            "files": [
                {
                    "id": "FIMG2",
                    "name": "photo.jpg",
                    "mimetype": "image/jpeg",
                    "url_private_download": "https://files.slack.com/files-pri/photo.jpg",
                }
            ],
        }
    }
    await ch._on_socket_request(_FakeSocketClient(), _FakeSocketRequest(payload))

    msg = bus.inbound.get_nowait()
    assert msg.media == [str(tmp_path / "FIMG2_photo.jpg")]
    assert "看这张图" in msg.content
    assert "[image:" in msg.content


@pytest.mark.asyncio
async def test_inbound_audio_file_triggers_transcription(tmp_path, monkeypatch) -> None:
    """Audio file_share: transcribe_audio is called; transcription included in content."""
    monkeypatch.setattr("nanobot.channels.slack.get_media_dir", lambda _: tmp_path)

    ch, bus = _make_channel()
    ch._http = _FakeHttpClient(content=b"audio-bytes")
    ch.transcription_api_key = "groq-key"

    async def _fake_transcribe(path):
        return "这是语音内容"

    monkeypatch.setattr(ch, "transcribe_audio", _fake_transcribe)

    payload = {
        "event": {
            "type": "message",
            "subtype": "file_share",
            "user": "U123",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1700000000.000300",
            "text": "",
            "files": [
                {
                    "id": "FAUD1",
                    "name": "voice.m4a",
                    "mimetype": "audio/mp4",
                    "url_private_download": "https://files.slack.com/files-pri/voice.m4a",
                }
            ],
        }
    }
    await ch._on_socket_request(_FakeSocketClient(), _FakeSocketRequest(payload))

    msg = bus.inbound.get_nowait()
    assert "这是语音内容" in msg.content


@pytest.mark.asyncio
async def test_inbound_file_download_failure_handled_gracefully(tmp_path, monkeypatch) -> None:
    """Download failure: message is still forwarded with failure tag, no crash."""
    monkeypatch.setattr("nanobot.channels.slack.get_media_dir", lambda _: tmp_path)

    ch, bus = _make_channel()

    class _FailHttpClient:
        async def get(self, url, *, headers=None, follow_redirects=False):
            raise OSError("connection refused")
        async def aclose(self) -> None:
            pass

    ch._http = _FailHttpClient()

    payload = {
        "event": {
            "type": "message",
            "subtype": "file_share",
            "user": "U123",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1700000000.000400",
            "text": "",
            "files": [
                {
                    "id": "FERR1",
                    "name": "broken.png",
                    "mimetype": "image/png",
                    "url_private_download": "https://files.slack.com/files-pri/broken.png",
                }
            ],
        }
    }
    await ch._on_socket_request(_FakeSocketClient(), _FakeSocketRequest(payload))

    msg = bus.inbound.get_nowait()
    assert msg.media == []
    assert "download failed" in msg.content


@pytest.mark.asyncio
async def test_inbound_file_too_large_skipped(tmp_path, monkeypatch) -> None:
    """Files exceeding MAX_ATTACHMENT_BYTES are skipped without downloading."""
    monkeypatch.setattr("nanobot.channels.slack.get_media_dir", lambda _: tmp_path)

    ch, bus = _make_channel()
    fake_http = _FakeHttpClient()
    ch._http = fake_http

    payload = {
        "event": {
            "type": "message",
            "subtype": "file_share",
            "user": "U123",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1700000000.000500",
            "text": "",
            "files": [
                {
                    "id": "FBIG1",
                    "name": "huge.png",
                    "mimetype": "image/png",
                    "size": 21 * 1024 * 1024,  # 21MB > 20MB limit
                    "url_private_download": "https://files.slack.com/files-pri/huge.png",
                }
            ],
        }
    }
    await ch._on_socket_request(_FakeSocketClient(), _FakeSocketRequest(payload))

    msg = bus.inbound.get_nowait()
    assert msg.media == []
    assert "too large" in msg.content
    assert len(fake_http.get_calls) == 0  # no download attempted


@pytest.mark.asyncio
async def test_inbound_file_path_traversal_sanitized(tmp_path, monkeypatch) -> None:
    """Malicious filenames with path components are reduced to basename only."""
    monkeypatch.setattr("nanobot.channels.slack.get_media_dir", lambda _: tmp_path)

    ch, bus = _make_channel()
    ch._http = _FakeHttpClient(content=b"data")

    payload = {
        "event": {
            "type": "message",
            "subtype": "file_share",
            "user": "U123",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1700000000.000600",
            "text": "",
            "files": [
                {
                    "id": "FPATH1",
                    "name": "../../etc/passwd",
                    "mimetype": "image/png",
                    "url_private_download": "https://files.slack.com/files-pri/evil.png",
                }
            ],
        }
    }
    await ch._on_socket_request(_FakeSocketClient(), _FakeSocketRequest(payload))

    msg = bus.inbound.get_nowait()
    # File should be written to tmp_path only — no directory traversal
    assert len(msg.media) == 1
    written_path = Path(msg.media[0])
    assert written_path.resolve().parent == tmp_path.resolve()
    assert written_path.name == "FPATH1_passwd"


@pytest.mark.asyncio
async def test_inbound_file_too_large_enforced_by_body_size(tmp_path, monkeypatch) -> None:
    """Files with no size metadata but oversized response body are rejected after download."""
    monkeypatch.setattr("nanobot.channels.slack.get_media_dir", lambda _: tmp_path)

    ch, bus = _make_channel()
    # size field absent (0), but response body exceeds limit
    oversized_content = b"x" * (21 * 1024 * 1024)
    ch._http = _FakeHttpClient(content=oversized_content)

    payload = {
        "event": {
            "type": "message",
            "subtype": "file_share",
            "user": "U123",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1700000000.000700",
            "text": "",
            "files": [
                {
                    "id": "FBIG2",
                    "name": "large_no_size.png",
                    "mimetype": "image/png",
                    # no "size" field
                    "url_private_download": "https://files.slack.com/files-pri/large.png",
                }
            ],
        }
    }
    await ch._on_socket_request(_FakeSocketClient(), _FakeSocketRequest(payload))

    msg = bus.inbound.get_nowait()
    assert msg.media == []
    assert "too large" in msg.content
