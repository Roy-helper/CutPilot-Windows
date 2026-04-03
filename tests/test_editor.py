"""Tests for core.editor — time span resolution, rough cut, cut_versions, VFR, cancel."""
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import core.editor as editor_mod
from core.editor import (
    CutResult, _detect_vfr, _get_fps_mode_flag, _parse_frame_rate,
    _resolve_time_spans, _run_ffmpeg_cmd, cut_versions, rough_cut,
)
from core.models import ScriptVersion, Sentence


# -- Fixtures ----------------------------------------------------------------


def _s(sid: int, start: float, end: float, text: str = "") -> Sentence:
    return Sentence(id=sid, start_sec=start, end_sec=end, text=text)


SENTENCES = [_s(1, 0.0, 2.0), _s(2, 2.0, 4.0), _s(3, 4.0, 6.0)]
SENTENCE_MAP = {s.id: s for s in SENTENCES}


@pytest.fixture(autouse=True)
def _clear_fps_cache():
    """Reset cached fps_mode flag between tests."""
    editor_mod._cached_fps_mode_flag = None
    yield
    editor_mod._cached_fps_mode_flag = None


# -- _resolve_time_spans -----------------------------------------------------


class TestResolveTimeSpans:
    def test_normal_mapping(self):
        spans = _resolve_time_spans([1, 3], SENTENCE_MAP)
        assert spans == [(0.0, 2.0), (4.0, 6.0)]

    def test_missing_ids_skipped(self):
        spans = _resolve_time_spans([1, 99], SENTENCE_MAP)
        assert spans == [(0.0, 2.0)]

    def test_empty_ids(self):
        spans = _resolve_time_spans([], SENTENCE_MAP)
        assert spans == []


# -- rough_cut ---------------------------------------------------------------


class TestRoughCut:
    @pytest.mark.asyncio
    async def test_no_time_spans_returns_failure(self):
        result = await rough_cut("/fake/video.mp4", [], "/fake/output.mp4")
        assert result.success is False
        assert "No time spans" in result.error

    @pytest.mark.asyncio
    async def test_success_returns_cut_result(self, tmp_path):
        output_path = str(tmp_path / "out.mp4")

        mock_probe = {"duration": 10.0, "width": 1920, "height": 1080, "has_audio": True, "is_vfr": False}

        with (
            patch("core.editor._probe_duration", return_value=60.0),
            patch("core.editor._run_ffmpeg_cmd"),
            patch("core.editor._validate_output", return_value=mock_probe),
            patch("core.editor._get_fps_mode_flag", return_value=["-fps_mode", "cfr"]),
        ):
            result = await rough_cut(
                "/fake/video.mp4",
                [(0.0, 2.0), (4.0, 6.0)],
                output_path,
            )

        assert result.success is True
        assert result.duration == 10.0
        assert result.width == 1920

    @pytest.mark.asyncio
    async def test_success_with_speed(self, tmp_path):
        output_path = str(tmp_path / "out_fast.mp4")

        mock_probe = {"duration": 8.0, "width": 1920, "height": 1080, "has_audio": True, "is_vfr": False}

        with (
            patch("core.editor._probe_duration", return_value=60.0),
            patch("core.editor._run_ffmpeg_cmd") as mock_cmd,
            patch("core.editor._validate_output", return_value=mock_probe),
            patch("core.editor._get_fps_mode_flag", return_value=["-fps_mode", "cfr"]),
        ):
            result = await rough_cut(
                "/fake/video.mp4",
                [(0.0, 2.0), (4.0, 6.0)],
                output_path,
                speed=1.25,
            )

        assert result.success is True
        # Verify the filter_complex contains speed filters
        cmd_args = mock_cmd.call_args[0][0]
        fc_idx = cmd_args.index("-filter_complex")
        filter_complex = cmd_args[fc_idx + 1]
        assert "atempo=1.2500" in filter_complex
        assert "setpts=0.8000*PTS" in filter_complex

    @pytest.mark.asyncio
    async def test_exception_returns_failure(self):
        with (
            patch("core.editor._probe_duration", return_value=60.0),
            patch("core.editor._run_ffmpeg_cmd", side_effect=RuntimeError("ffmpeg exploded")),
            patch("core.editor._get_fps_mode_flag", return_value=["-vsync", "cfr"]),
        ):
            result = await rough_cut("/fake/video.mp4", [(0.0, 2.0)], "/tmp/out.mp4")

        assert result.success is False
        assert "ffmpeg exploded" in result.error

    @pytest.mark.asyncio
    async def test_clamp_out_of_range_spans(self, tmp_path):
        """Spans beyond source duration should be clamped, not crash."""
        output_path = str(tmp_path / "out.mp4")
        mock_probe = {"duration": 2.0, "width": 1920, "height": 1080, "has_audio": True, "is_vfr": False}

        with (
            patch("core.editor._probe_duration", return_value=5.0),
            patch("core.editor._run_ffmpeg_cmd"),
            patch("core.editor._validate_output", return_value=mock_probe),
            patch("core.editor._get_fps_mode_flag", return_value=["-fps_mode", "cfr"]),
        ):
            result = await rough_cut(
                "/fake/video.mp4",
                [(0.0, 2.0), (10.0, 20.0)],
                output_path,
            )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_fps_mode_flag_in_command(self, tmp_path):
        """FFmpeg command must contain -fps_mode or -vsync for VFR compat."""
        output_path = str(tmp_path / "out.mp4")
        mock_probe = {"duration": 4.0, "width": 1920, "height": 1080, "has_audio": True, "is_vfr": False}

        with (
            patch("core.editor._probe_duration", return_value=60.0),
            patch("core.editor._run_ffmpeg_cmd") as mock_cmd,
            patch("core.editor._validate_output", return_value=mock_probe),
            patch("core.editor._get_fps_mode_flag", return_value=["-fps_mode", "cfr"]),
        ):
            await rough_cut("/fake/video.mp4", [(0.0, 2.0)], output_path)

        cmd_args = mock_cmd.call_args[0][0]
        assert "-fps_mode" in cmd_args
        assert "cfr" in cmd_args

    @pytest.mark.asyncio
    async def test_aresample_in_filter_complex(self, tmp_path):
        """Audio filters must include aresample=async=1 for drift prevention."""
        output_path = str(tmp_path / "out.mp4")
        mock_probe = {"duration": 4.0, "width": 1920, "height": 1080, "has_audio": True, "is_vfr": False}

        with (
            patch("core.editor._probe_duration", return_value=60.0),
            patch("core.editor._run_ffmpeg_cmd") as mock_cmd,
            patch("core.editor._validate_output", return_value=mock_probe),
            patch("core.editor._get_fps_mode_flag", return_value=["-fps_mode", "cfr"]),
        ):
            await rough_cut("/fake/video.mp4", [(0.0, 2.0)], output_path)

        cmd_args = mock_cmd.call_args[0][0]
        fc_idx = cmd_args.index("-filter_complex")
        filter_complex = cmd_args[fc_idx + 1]
        assert "aresample=async=1" in filter_complex


# -- VFR detection -----------------------------------------------------------


class TestVfrDetection:
    def test_cfr_video_not_vfr(self):
        stream = {"r_frame_rate": "30/1", "avg_frame_rate": "30/1"}
        assert _detect_vfr(stream, "test.mp4") is False

    def test_vfr_video_detected(self):
        # Phone recording: r_frame_rate=90000/1001 (~89.9), avg=29.97
        stream = {"r_frame_rate": "90000/1001", "avg_frame_rate": "30000/1001"}
        assert _detect_vfr(stream, "test.mp4") is True

    def test_slight_difference_not_vfr(self):
        # 2% difference — within threshold
        stream = {"r_frame_rate": "30/1", "avg_frame_rate": "30600/1001"}
        assert _detect_vfr(stream, "test.mp4") is False

    def test_missing_rates_not_vfr(self):
        stream = {}
        assert _detect_vfr(stream, "test.mp4") is False

    def test_parse_frame_rate_fraction(self):
        assert abs(_parse_frame_rate("30000/1001") - 29.97) < 0.01

    def test_parse_frame_rate_integer(self):
        assert _parse_frame_rate("30") == 30.0

    def test_parse_frame_rate_empty(self):
        assert _parse_frame_rate("") == 0.0


# -- _get_fps_mode_flag ------------------------------------------------------


class TestGetFpsModeFlag:
    def test_new_ffmpeg_uses_fps_mode(self):
        mock_result = MagicMock()
        mock_result.stdout = "ffmpeg version 6.1.2 Copyright (c) 2000-2024"
        with patch("core.editor.run_hidden", return_value=mock_result):
            assert _get_fps_mode_flag() == ["-fps_mode", "cfr"]

    def test_old_ffmpeg_uses_vsync(self):
        mock_result = MagicMock()
        mock_result.stdout = "ffmpeg version 4.4.1 Copyright (c) 2000-2021"
        with patch("core.editor.run_hidden", return_value=mock_result):
            assert _get_fps_mode_flag() == ["-vsync", "cfr"]

    def test_ffmpeg_5_1_uses_fps_mode(self):
        mock_result = MagicMock()
        mock_result.stdout = "ffmpeg version 5.1 Copyright (c) 2000-2022"
        with patch("core.editor.run_hidden", return_value=mock_result):
            assert _get_fps_mode_flag() == ["-fps_mode", "cfr"]

    def test_ffmpeg_not_found_fallback(self):
        with patch("core.editor.run_hidden", side_effect=FileNotFoundError):
            assert _get_fps_mode_flag() == ["-vsync", "cfr"]


# -- cut_versions ------------------------------------------------------------


# -- Cancel support ----------------------------------------------------------


class TestCancelSupport:
    def test_cancel_event_terminates_process(self):
        """When cancel_event is set, _run_ffmpeg_cmd should kill the process."""
        cancel_event = threading.Event()
        cancel_event.set()  # Already cancelled

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # process running
        mock_proc.terminate.return_value = None
        mock_proc.wait.return_value = None
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.read.return_value = b""

        with patch("core.editor.popen_hidden", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="取消"):
                _run_ffmpeg_cmd(["ffmpeg", "-y"], cancel_event=cancel_event)

        mock_proc.terminate.assert_called_once()

    def test_no_cancel_event_uses_subprocess_run(self):
        """Without cancel_event, _run_ffmpeg_cmd should use blocking subprocess.run."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = b""

        with patch("core.editor.run_hidden", return_value=mock_result) as mock_run:
            _run_ffmpeg_cmd(["ffmpeg", "-y"], cancel_event=None)

        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_rough_cut_cleans_output_on_cancel(self, tmp_path):
        """Cancelled rough_cut should remove incomplete output file."""
        output_path = str(tmp_path / "incomplete.mp4")
        # Create a dummy file to simulate incomplete output
        Path(output_path).write_text("incomplete")

        cancel_event = threading.Event()
        cancel_event.set()

        with (
            patch("core.editor._probe_duration", return_value=60.0),
            patch("core.editor._run_ffmpeg_cmd", side_effect=RuntimeError("用户取消处理")),
            patch("core.editor._get_fps_mode_flag", return_value=["-fps_mode", "cfr"]),
        ):
            result = await rough_cut(
                "/fake/video.mp4", [(0.0, 2.0)], output_path,
                cancel_event=cancel_event,
            )

        assert result.success is False
        assert "取消" in result.error
        # Incomplete output should be cleaned up
        assert not Path(output_path).exists()


# -- cut_versions ------------------------------------------------------------


class TestCutVersions:
    @pytest.mark.asyncio
    async def test_output_list_structure(self, tmp_path):
        version = ScriptVersion(version_id=1, sentence_ids=[1, 2])

        mock_cut_result = CutResult(
            output_path=str(tmp_path / "test_v1.mp4"),
            duration=4.0,
            width=1920,
            height=1080,
            success=True,
        )

        config = MagicMock()
        config.output_dir = str(tmp_path)
        config.generate_fast = False
        config.enable_hook_overlay = False
        config.video_quality = "standard"

        with patch("core.editor.rough_cut", new_callable=AsyncMock, return_value=mock_cut_result):
            results = await cut_versions(
                tmp_path / "source.mp4",
                [version],
                SENTENCES,
                config,
            )

        assert len(results) == 1
        assert results[0]["version_id"] == 1
        assert results[0]["speed"] == "normal"
        assert "path" in results[0]

    @pytest.mark.asyncio
    async def test_with_fast_variant(self, tmp_path):
        version = ScriptVersion(version_id=1, sentence_ids=[1, 2])

        mock_cut_result = CutResult(
            output_path=str(tmp_path / "test_v1.mp4"),
            duration=4.0,
            width=1920,
            height=1080,
            success=True,
        )

        config = MagicMock()
        config.output_dir = str(tmp_path)
        config.generate_fast = True
        config.enable_hook_overlay = False
        config.video_quality = "standard"

        with patch("core.editor.rough_cut", new_callable=AsyncMock, return_value=mock_cut_result):
            results = await cut_versions(
                tmp_path / "source.mp4",
                [version],
                SENTENCES,
                config,
            )

        assert len(results) == 2
        speeds = [r["speed"] for r in results]
        assert "normal" in speeds
        assert "fast" in speeds
