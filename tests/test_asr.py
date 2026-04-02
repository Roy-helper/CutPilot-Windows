"""Tests for core.asr — model download with progress, timeout, and error messages."""
from unittest.mock import MagicMock, patch
from concurrent.futures import TimeoutError as FuturesTimeout

from core.asr import download_model


class TestDownloadModel:
    def test_success_calls_on_progress(self):
        progress_calls = []

        def on_progress(pct: int) -> None:
            progress_calls.append(pct)

        with patch("huggingface_hub.snapshot_download"):
            result = download_model(engine="faster-whisper", on_progress=on_progress)

        assert result["success"] is True
        assert 0 in progress_calls
        assert 100 in progress_calls

    def test_success_without_progress(self):
        with patch("huggingface_hub.snapshot_download"):
            result = download_model(engine="faster-whisper")

        assert result["success"] is True
        assert "完成" in result["message"]

    def test_network_error_shows_manual_instructions(self):
        with patch("huggingface_hub.snapshot_download", side_effect=ConnectionError("Connection refused")):
            result = download_model(engine="faster-whisper")

        assert result["success"] is False
        assert "hf-mirror.com" in result["message"]
        assert "手动下载" in result["message"]

    def test_generic_error_shows_manual_instructions(self):
        with patch("huggingface_hub.snapshot_download", side_effect=RuntimeError("disk full")):
            result = download_model(engine="faster-whisper")

        assert result["success"] is False
        assert "hf-mirror.com" in result["message"]
        assert "disk full" in result["message"]

    def test_timeout_error_shows_manual_instructions(self):
        def slow_download(*args, **kwargs):
            raise FuturesTimeout("timed out")

        with patch("huggingface_hub.snapshot_download", side_effect=slow_download):
            result = download_model(engine="faster-whisper")

        assert result["success"] is False
        assert "hf-mirror.com" in result["message"]

    def test_funasr_delegates_to_funasr_download(self):
        with patch("core.asr._download_funasr_model", return_value={"success": True, "message": "ok"}) as mock:
            result = download_model(engine="funasr")

        assert result["success"] is True
        mock.assert_called_once()
