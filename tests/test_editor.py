"""Tests for core.editor — time span resolution, rough cut, cut_versions."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.editor import CutResult, _resolve_time_spans, cut_versions, rough_cut
from core.models import ScriptVersion, Sentence


# -- Fixtures ----------------------------------------------------------------


def _s(sid: int, start: float, end: float, text: str = "") -> Sentence:
    return Sentence(id=sid, start_sec=start, end_sec=end, text=text)


SENTENCES = [_s(1, 0.0, 2.0), _s(2, 2.0, 4.0), _s(3, 4.0, 6.0)]
SENTENCE_MAP = {s.id: s for s in SENTENCES}


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

        mock_probe = {"duration": 10.0, "width": 1920, "height": 1080, "has_audio": True}

        with (
            patch("core.editor._moviepy_cut_and_concat") as mock_cut,
            patch("core.editor._validate_output", new_callable=AsyncMock, return_value=mock_probe),
        ):
            result = await rough_cut(
                "/fake/video.mp4",
                [(0.0, 2.0), (4.0, 6.0)],
                output_path,
            )

        assert result.success is True
        assert result.duration == 10.0
        assert result.width == 1920
        mock_cut.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_returns_failure(self):
        with patch(
            "core.editor._moviepy_cut_and_concat",
            side_effect=RuntimeError("MoviePy exploded"),
        ):
            result = await rough_cut("/fake/video.mp4", [(0.0, 2.0)], "/tmp/out.mp4")

        assert result.success is False
        assert "MoviePy exploded" in result.error


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

        with (
            patch("core.editor.rough_cut", new_callable=AsyncMock, return_value=mock_cut_result),
            patch("core.editor._run_ffmpeg", new_callable=AsyncMock),
        ):
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
