"""Tests for core.overlay — subprocess.run migration, non-ASCII path protection,
Chinese paths, empty text, PIL fallback."""
import asyncio
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from core.overlay import (
    _needs_temp_copy, _probe_video_dimensions, _ffmpeg_overlay,
    burn_hook_overlay, create_hook_image,
)


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

        with patch("core.overlay.run_hidden", return_value=mock_result) as mock_run:
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
            patch("core.overlay.run_hidden", return_value=mock_result) as mock_run,
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


# -- Chinese paths (source and output) ----------------------------------------


class TestChinesePaths:
    def test_chinese_source_uses_temp_copy(self):
        """Chinese source path on Windows triggers temp copy."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = b""

        with (
            patch("core.overlay.sys") as mock_sys,
            patch("core.overlay.run_hidden", return_value=mock_result) as mock_run,
            patch("core.overlay.shutil.copy2") as mock_copy,
            patch("core.editor._get_fps_mode_flag", return_value=["-fps_mode", "cfr"]),
        ):
            mock_sys.platform = "win32"
            _ffmpeg_overlay(
                Path("C:/视频素材/原片.mp4"),
                Path("C:/tmp/overlay.png"),
                Path("C:/output/result.mp4"),
                3.0,
            )

        # source had Chinese chars → should have copied to temp
        mock_copy.assert_called_once()
        # FFmpeg command should NOT contain the original Chinese path
        cmd = mock_run.call_args[0][0]
        input_paths = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-i"]
        for p in input_paths:
            if p != str(Path("C:/tmp/overlay.png")):
                # The video input should be an ASCII temp path
                try:
                    p.encode("ascii")
                except UnicodeEncodeError:
                    pytest.fail(f"FFmpeg received non-ASCII input path: {p}")

    def test_chinese_output_uses_temp_then_moves(self):
        """Chinese output path on Windows writes to temp, then moves."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = b""

        with (
            patch("core.overlay.sys") as mock_sys,
            patch("core.overlay.run_hidden", return_value=mock_result),
            patch("core.overlay.shutil.copy2"),
            patch("core.overlay.shutil.move") as mock_move,
            patch("core.editor._get_fps_mode_flag", return_value=["-fps_mode", "cfr"]),
        ):
            mock_sys.platform = "win32"
            _ffmpeg_overlay(
                Path("C:/video/source.mp4"),
                Path("C:/tmp/overlay.png"),
                Path("C:/输出目录/结果.mp4"),
                3.0,
            )

        # Output had Chinese chars → should have moved from temp
        mock_move.assert_called_once()

    def test_probe_chinese_path_uses_temp(self):
        """ffprobe with Chinese path on Windows uses a temp copy."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'{"streams": [{"width": 1280, "height": 720}]}'
        mock_result.stderr = b""

        with (
            patch("core.overlay.sys") as mock_sys,
            patch("core.overlay.run_hidden", return_value=mock_result),
            patch("core.overlay.shutil.copy2") as mock_copy,
        ):
            mock_sys.platform = "win32"
            result = _probe_video_dimensions(Path("C:/视频/测试.mp4"))

        assert result == {"width": 1280, "height": 720}
        mock_copy.assert_called_once()


# -- Empty text ---------------------------------------------------------------


class TestEmptyText:
    @pytest.mark.asyncio
    async def test_empty_string_returns_original_path(self):
        """burn_hook_overlay with empty text should return the original path."""
        video_path = Path("C:/fake/video.mp4")
        result = await burn_hook_overlay(video_path, "")
        assert result == video_path

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_original_path(self):
        """burn_hook_overlay with whitespace-only text returns original."""
        video_path = Path("C:/fake/video.mp4")
        result = await burn_hook_overlay(video_path, "   \n  ")
        assert result == video_path


# -- PIL render failure fallback ----------------------------------------------


class TestPilFallback:
    @pytest.mark.asyncio
    async def test_no_cjk_font_returns_original(self):
        """When no CJK font is found, overlay is skipped gracefully."""
        video_path = Path("C:/fake/video.mp4")

        with (
            patch("core.overlay._probe_video_dimensions", return_value={"width": 1920, "height": 1080}),
            patch("core.overlay.find_cjk_font", return_value=None),
        ):
            result = await burn_hook_overlay(video_path, "测试文字")

        assert result == video_path

    def test_create_hook_image_no_font_returns_none(self):
        """create_hook_image returns None when no CJK font is available."""
        with patch("core.overlay.find_cjk_font", return_value=None):
            result = create_hook_image("测试", 1920, 1080)
        assert result is None

    @pytest.mark.asyncio
    async def test_render_exception_returns_original(self):
        """If PIL rendering raises, burn_hook_overlay returns original path."""
        video_path = Path("C:/fake/video.mp4")

        with (
            patch("core.overlay._probe_video_dimensions", return_value={"width": 1920, "height": 1080}),
            patch("core.overlay.find_cjk_font", return_value="/fake/font.ttf"),
            patch("core.overlay.render_text_card", side_effect=OSError("font broken")),
        ):
            result = await burn_hook_overlay(video_path, "测试文字")

        assert result == video_path

    @pytest.mark.asyncio
    async def test_ffmpeg_overlay_failure_returns_original(self):
        """If FFmpeg overlay fails, burn_hook_overlay returns original path."""
        video_path = Path("C:/fake/video.mp4")

        with (
            patch("core.overlay._probe_video_dimensions", return_value={"width": 1920, "height": 1080}),
            patch("core.overlay.create_hook_image") as mock_img,
            patch("core.overlay._ffmpeg_overlay", side_effect=RuntimeError("ffmpeg exploded")),
        ):
            # create_hook_image returns a mock PNG path
            mock_png = MagicMock(spec=Path)
            mock_png.unlink = MagicMock()
            mock_img.return_value = mock_png

            result = await burn_hook_overlay(video_path, "测试文字")

        assert result == video_path
        # Temp PNG should be cleaned up even on failure
        mock_png.unlink.assert_called_once()
