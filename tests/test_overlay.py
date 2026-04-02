"""Tests for core.overlay — subprocess.run migration, non-ASCII path protection."""
from unittest.mock import MagicMock, patch
from pathlib import Path

from core.overlay import _needs_temp_copy, _probe_video_dimensions, _ffmpeg_overlay


class TestNeedsTempCopy:
    def test_ascii_path_on_windows(self):
        with patch("core.overlay.sys") as mock_sys:
            mock_sys.platform = "win32"
            assert _needs_temp_copy("/path/to/video.mp4") is False

    def test_chinese_path_on_windows(self):
        with patch("core.overlay.sys") as mock_sys:
            mock_sys.platform = "win32"
            assert _needs_temp_copy("/path/到/视频.mp4") is True

    def test_chinese_path_on_linux(self):
        with patch("core.overlay.sys") as mock_sys:
            mock_sys.platform = "linux"
            assert _needs_temp_copy("/path/到/视频.mp4") is False


class TestProbeVideoDimensions:
    def test_uses_subprocess_run(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'{"streams": [{"width": 1920, "height": 1080}]}'
        mock_result.stderr = b""

        with patch("core.overlay.subprocess.run", return_value=mock_result) as mock_run:
            result = _probe_video_dimensions(Path("/fake/video.mp4"))

        assert result == {"width": 1920, "height": 1080}
        mock_run.assert_called_once()
        # Verify it's subprocess.run, not asyncio
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffprobe"


class TestFfmpegOverlay:
    def test_uses_subprocess_run(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = b""

        with (
            patch("core.overlay.subprocess.run", return_value=mock_result) as mock_run,
            patch("core.editor._get_fps_mode_flag", return_value=["-fps_mode", "cfr"]),
        ):
            _ffmpeg_overlay(
                Path("/fake/video.mp4"),
                Path("/tmp/overlay.png"),
                Path("/fake/output.mp4"),
                3.0,
            )

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-fps_mode" in cmd
