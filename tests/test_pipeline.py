"""Tests for core.pipeline — full flow, error paths, cache hits, copy text, cancel, batch, stage runners."""
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.cache_manager import CacheManager
from core.models import ProcessResult, ScriptVersion, Sentence
from core.pipeline import (
    _format_srt_time, _has_audio_stream, _report_progress, _run_asr,
    _run_director, _run_editor, _run_inspector, build_batch_summary,
    export_srt, generate_copy_text, process_batch, process_video,
)


# -- Fixtures ----------------------------------------------------------------


def _s(sid: int, start: float, end: float, text: str = "句子") -> Sentence:
    return Sentence(id=sid, start_sec=start, end_sec=end, text=text)


def _make_sentences(n: int) -> list[Sentence]:
    return [_s(i + 1, float(i), float(i + 1), f"句子{i + 1}") for i in range(n)]


def _make_config(**overrides):
    config = MagicMock()
    config.min_sentences = 15
    config.max_versions = 3
    config.output_dir = ""
    config.generate_fast = False
    for k, v in overrides.items():
        setattr(config, k, v)
    return config


APPROVED_VERSION = ScriptVersion(
    version_id=1,
    title="V1",
    sentence_ids=[1, 2, 3],
    approach_tag="痛点解决",
    publish_text="发布文案",
    cover_title="封面标题",
    cover_subtitle="副标题",
    tags=["tag1", "tag2"],
)


# -- process_video: video not found ------------------------------------------


class TestProcessVideoErrors:
    @pytest.mark.asyncio
    async def test_video_not_found(self, tmp_path):
        config = _make_config()
        result = await process_video(tmp_path / "missing.mp4", config)
        assert result.success is False
        assert "不存在" in result.error

    @pytest.mark.asyncio
    async def test_too_few_sentences(self, tmp_path):
        video = tmp_path / "short.mp4"
        video.write_bytes(b"fake")

        few_sentences = _make_sentences(5)
        cache = CacheManager(base_dir=tmp_path / "cache")

        with patch("core.pipeline._run_asr", new_callable=AsyncMock, return_value=few_sentences):
            config = _make_config(min_sentences=15)
            result = await process_video(video, config, cache=cache)

        assert result.success is False
        assert "太短" in result.error


# -- process_video: full flow ------------------------------------------------


class TestProcessVideoFullFlow:
    @pytest.mark.asyncio
    async def test_mock_all_stages(self, tmp_path):
        video = tmp_path / "source.mp4"
        video.write_bytes(b"fake video")

        sentences = _make_sentences(20)
        versions = [APPROVED_VERSION]
        output_files = [{"version_id": 1, "path": "/out/v1.mp4", "speed": "normal"}]

        cache = CacheManager(base_dir=tmp_path / "cache")

        with (
            patch("core.pipeline._run_asr", new_callable=AsyncMock, return_value=sentences),
            patch("core.pipeline._run_director", new_callable=AsyncMock, return_value=versions),
            patch("core.pipeline._run_inspector", new_callable=AsyncMock, return_value=versions),
            patch("core.pipeline._run_editor", new_callable=AsyncMock, return_value=output_files),
        ):
            config = _make_config(min_sentences=15)
            result = await process_video(video, config, cache=cache)

        assert result.success is True
        assert len(result.versions) == 1
        assert len(result.output_files) == 1


# -- process_video: cache hit path -------------------------------------------


class TestProcessVideoCacheHit:
    @pytest.mark.asyncio
    async def test_cached_asr_loaded(self, tmp_path):
        video = tmp_path / "source.mp4"
        video.write_bytes(b"fake video")

        sentences = _make_sentences(20)
        versions = [APPROVED_VERSION]
        output_files = [{"version_id": 1, "path": "/out/v1.mp4", "speed": "normal"}]

        cache = CacheManager(base_dir=tmp_path / "cache")
        # Pre-populate ASR cache
        cache.save(video, "asr", [s.model_dump() for s in sentences])

        with (
            patch("core.pipeline._run_director", new_callable=AsyncMock, return_value=versions),
            patch("core.pipeline._run_inspector", new_callable=AsyncMock, return_value=versions),
            patch("core.pipeline._run_editor", new_callable=AsyncMock, return_value=output_files),
        ):
            config = _make_config(min_sentences=15)
            result = await process_video(video, config, cache=cache)

        assert result.success is True


# -- generate_copy_text ------------------------------------------------------


class TestGenerateCopyText:
    def test_output_format(self):
        versions = [
            ScriptVersion(
                version_id=1,
                approach_tag="痛点解决",
                publish_text="文案1",
                cover_title="标题1",
                cover_subtitle="副标题1",
                tags=["t1", "t2"],
            ),
            ScriptVersion(
                version_id=2,
                approach_tag="",
                publish_text="文案2",
                cover_title="标题2",
                cover_subtitle="副标题2",
                tags=["t3"],
            ),
        ]
        text = generate_copy_text(versions)

        assert "=== V1 [痛点解决] ===" in text
        assert "=== V2 ===" in text
        assert "发布文案: 文案1" in text
        assert "封面主标题: 标题2" in text
        assert "封面副标题: 副标题1" in text
        assert "标签: t1 t2" in text
        assert text.endswith("\n")

    def test_empty_versions(self):
        text = generate_copy_text([])
        assert text == "\n"


# -- build_batch_summary ----------------------------------------------------


class TestBuildBatchSummary:
    def test_all_success(self):
        paths = [Path("a.mp4"), Path("b.mp4"), Path("c.mp4")]
        results = [
            ProcessResult(success=True),
            ProcessResult(success=True),
            ProcessResult(success=True),
        ]
        summary = build_batch_summary(paths, results)
        assert summary["total"] == 3
        assert summary["success_count"] == 3
        assert summary["fail_count"] == 0
        assert summary["errors"] == []

    def test_mixed_results(self):
        paths = [Path("a.mp4"), Path("b.mp4"), Path("c.mp4")]
        results = [
            ProcessResult(success=True),
            ProcessResult(success=False, error="ASR 失败"),
            ProcessResult(success=True),
        ]
        summary = build_batch_summary(paths, results)
        assert summary["total"] == 3
        assert summary["success_count"] == 2
        assert summary["fail_count"] == 1
        assert len(summary["errors"]) == 1
        assert summary["errors"][0]["video"] == "b.mp4"
        assert summary["errors"][0]["error"] == "ASR 失败"

    def test_all_fail(self):
        paths = [Path("x.mp4"), Path("y.mp4")]
        results = [
            ProcessResult(success=False, error="错误1"),
            ProcessResult(success=False, error="错误2"),
        ]
        summary = build_batch_summary(paths, results)
        assert summary["success_count"] == 0
        assert summary["fail_count"] == 2
        assert len(summary["errors"]) == 2


# -- cancel_event -----------------------------------------------------------


class TestCancelEvent:
    @pytest.mark.asyncio
    async def test_cancel_before_asr(self, tmp_path):
        video = tmp_path / "source.mp4"
        video.write_bytes(b"fake")
        cancel = threading.Event()
        cancel.set()  # Already cancelled

        config = _make_config()
        result = await process_video(video, config, cancel_event=cancel)
        assert result.success is False
        assert "取消" in result.error

    @pytest.mark.asyncio
    async def test_cancel_after_asr(self, tmp_path):
        video = tmp_path / "source.mp4"
        video.write_bytes(b"fake")
        cancel = threading.Event()

        sentences = _make_sentences(20)

        async def asr_then_cancel(*args, **kwargs):
            cancel.set()  # Cancel after ASR completes
            return sentences

        config = _make_config(min_sentences=15)
        cache = CacheManager(base_dir=tmp_path / "cache")

        with patch("core.pipeline._run_asr", side_effect=asr_then_cancel):
            result = await process_video(video, config, cache=cache, cancel_event=cancel)

        assert result.success is False
        assert "取消" in result.error

    @pytest.mark.asyncio
    async def test_cancel_after_director(self, tmp_path):
        video = tmp_path / "source.mp4"
        video.write_bytes(b"fake")
        cancel = threading.Event()

        sentences = _make_sentences(20)
        versions = [APPROVED_VERSION]

        async def director_then_cancel(*args, **kwargs):
            cancel.set()
            return versions

        config = _make_config(min_sentences=15)
        cache = CacheManager(base_dir=tmp_path / "cache")

        with (
            patch("core.pipeline._run_asr", new_callable=AsyncMock, return_value=sentences),
            patch("core.pipeline._run_director", side_effect=director_then_cancel),
        ):
            result = await process_video(video, config, cache=cache, cancel_event=cancel)

        assert result.success is False
        assert "取消" in result.error


# -- _report_progress -------------------------------------------------------


class TestReportProgress:
    def test_calls_callback(self):
        calls = []
        _report_progress(lambda l, p: calls.append((l, p)), "ASR", 50)
        assert calls == [("ASR", 50)]

    def test_none_callback_is_noop(self):
        _report_progress(None, "ASR", 50)  # should not raise


# -- process_batch -----------------------------------------------------------


class TestProcessBatch:
    @pytest.mark.asyncio
    async def test_returns_results_for_all_videos(self, tmp_path):
        v1 = tmp_path / "a.mp4"
        v2 = tmp_path / "b.mp4"
        v1.write_bytes(b"fake")
        v2.write_bytes(b"fake")

        sentences = _make_sentences(20)
        versions = [APPROVED_VERSION]
        output_files = [{"version_id": 1, "path": "/out/v1.mp4"}]

        config = _make_config(min_sentences=15)
        cache = CacheManager(base_dir=tmp_path / "cache")

        with (
            patch("core.pipeline._run_asr", new_callable=AsyncMock, return_value=sentences),
            patch("core.pipeline._run_director", new_callable=AsyncMock, return_value=versions),
            patch("core.pipeline._run_inspector", new_callable=AsyncMock, return_value=versions),
            patch("core.pipeline._run_editor", new_callable=AsyncMock, return_value=output_files),
        ):
            results = await process_batch(
                [v1, v2], config, cache=cache, max_parallel=2,
            )

        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_batch_cancel_returns_cancelled(self, tmp_path):
        v1 = tmp_path / "a.mp4"
        v1.write_bytes(b"fake")
        cancel = threading.Event()
        cancel.set()

        config = _make_config()
        results = await process_batch(
            [v1], config, max_parallel=1, cancel_event=cancel,
        )
        assert len(results) == 1
        assert results[0].success is False
        assert "取消" in results[0].error

    @pytest.mark.asyncio
    async def test_batch_isolates_failures(self, tmp_path):
        good = tmp_path / "good.mp4"
        good.write_bytes(b"fake")
        bad = tmp_path / "missing.mp4"  # doesn't exist

        sentences = _make_sentences(20)
        versions = [APPROVED_VERSION]
        output_files = [{"version_id": 1, "path": "/out/v1.mp4"}]

        config = _make_config(min_sentences=15)
        cache = CacheManager(base_dir=tmp_path / "cache")

        with (
            patch("core.pipeline._run_asr", new_callable=AsyncMock, return_value=sentences),
            patch("core.pipeline._run_director", new_callable=AsyncMock, return_value=versions),
            patch("core.pipeline._run_inspector", new_callable=AsyncMock, return_value=versions),
            patch("core.pipeline._run_editor", new_callable=AsyncMock, return_value=output_files),
        ):
            results = await process_batch(
                [good, bad], config, cache=cache, max_parallel=2,
            )

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False


# -- Stage runner unit tests ------------------------------------------------


class TestRunAsr:
    @pytest.mark.asyncio
    async def test_cache_miss_calls_transcribe(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        cache = CacheManager(base_dir=tmp_path / "cache")
        config = _make_config(enable_speaker_diarization=False, asr_engine="faster-whisper")

        mock_seg = MagicMock(start=0.0, end=1.0, text="hello", speaker=None)
        with (
            patch("core.pipeline._has_audio_stream", return_value=True),
            patch("core.asr.transcribe_video", new_callable=AsyncMock, return_value=[mock_seg]),
        ):
            result = await _run_asr(video, config, cache, "", None)

        assert len(result) == 1
        assert result[0].text == "hello"
        assert cache.exists(video, "asr")  # saved to cache

    @pytest.mark.asyncio
    async def test_cache_hit_skips_transcribe(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        cache = CacheManager(base_dir=tmp_path / "cache")
        config = _make_config()

        sentences = _make_sentences(3)
        cache.save(video, "asr", [s.model_dump() for s in sentences])

        # transcribe_video should NOT be called
        result = await _run_asr(video, config, cache, "", None)
        assert len(result) == 3


class TestRunDirector:
    @pytest.mark.asyncio
    async def test_cache_miss_calls_generate(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        cache = CacheManager(base_dir=tmp_path / "cache")
        config = _make_config(max_versions=3)
        sentences = _make_sentences(20)

        with patch("core.director.generate_versions", new_callable=AsyncMock, return_value=[APPROVED_VERSION]):
            result = await _run_director(sentences, config, cache, video, None)

        assert len(result) == 1
        assert cache.exists(video, "director")

    @pytest.mark.asyncio
    async def test_cache_hit(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        cache = CacheManager(base_dir=tmp_path / "cache")
        config = _make_config()

        cache.save(video, "director", [APPROVED_VERSION.model_dump()])
        result = await _run_director([], config, cache, video, None)
        assert len(result) == 1


class TestRunInspector:
    @pytest.mark.asyncio
    async def test_cache_miss_calls_review(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        cache = CacheManager(base_dir=tmp_path / "cache")
        config = _make_config()
        sentences = _make_sentences(20)

        with patch("core.inspector.review_versions", new_callable=AsyncMock, return_value=[APPROVED_VERSION]):
            result = await _run_inspector([APPROVED_VERSION], sentences, config, cache, video, None)

        assert len(result) == 1
        assert cache.exists(video, "inspector")

    @pytest.mark.asyncio
    async def test_cache_hit(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        cache = CacheManager(base_dir=tmp_path / "cache")
        config = _make_config()

        cache.save(video, "inspector", [APPROVED_VERSION.model_dump()])
        result = await _run_inspector([], [], config, cache, video, None)
        assert len(result) == 1


class TestRunEditor:
    @pytest.mark.asyncio
    async def test_calls_cut_versions(self, tmp_path):
        video = tmp_path / "video.mp4"
        cache = CacheManager(base_dir=tmp_path / "cache")
        config = _make_config()
        sentences = _make_sentences(5)
        output = [{"version_id": 1, "path": "/out.mp4"}]

        with patch("core.editor.cut_versions", new_callable=AsyncMock, return_value=output):
            result = await _run_editor(video, [APPROVED_VERSION], sentences, config, cache, None)

        assert result == output


# -- process_video: empty versions / empty approved -------------------------


class TestHasAudioStream:
    def test_with_audio(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'{"streams": [{"codec_type": "audio"}]}'
        with patch("subprocess.run", return_value=mock_result):
            assert _has_audio_stream(Path("/fake/video.mp4")) is True

    def test_without_audio(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b'{"streams": []}'
        with patch("subprocess.run", return_value=mock_result):
            assert _has_audio_stream(Path("/fake/video.mp4")) is False

    def test_ffprobe_error_returns_false(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert _has_audio_stream(Path("/fake/video.mp4")) is False


class TestNoAudioDetection:
    @pytest.mark.asyncio
    async def test_no_audio_video_fails(self, tmp_path):
        video = tmp_path / "silent.mp4"
        video.write_bytes(b"fake")
        cache = CacheManager(base_dir=tmp_path / "cache")
        config = _make_config(min_sentences=15)

        with patch("core.pipeline._has_audio_stream", return_value=False):
            result = await process_video(video, config, cache=cache)

        assert result.success is False
        assert "无音频" in result.error


class TestSrtExport:
    def test_format_srt_time(self):
        assert _format_srt_time(0.0) == "00:00:00,000"
        assert _format_srt_time(65.5) == "00:01:05,500"
        assert _format_srt_time(3661.123) == "01:01:01,123"

    def test_export_srt_writes_file(self, tmp_path):
        sentences = _make_sentences(3)
        srt_path = tmp_path / "test.srt"
        export_srt(sentences, srt_path)

        content = srt_path.read_text(encoding="utf-8")
        assert "1\n" in content
        assert "2\n" in content
        assert "3\n" in content
        assert "-->" in content
        assert "句子1" in content


class TestProcessVideoEdgeCases:
    @pytest.mark.asyncio
    async def test_no_versions_from_director(self, tmp_path):
        video = tmp_path / "source.mp4"
        video.write_bytes(b"fake")
        sentences = _make_sentences(20)
        cache = CacheManager(base_dir=tmp_path / "cache")

        with (
            patch("core.pipeline._run_asr", new_callable=AsyncMock, return_value=sentences),
            patch("core.pipeline._run_director", new_callable=AsyncMock, return_value=[]),
        ):
            config = _make_config(min_sentences=15)
            result = await process_video(video, config, cache=cache)

        assert result.success is False
        assert "有效版本" in result.error or "编导" in result.error

    @pytest.mark.asyncio
    async def test_no_approved_versions(self, tmp_path):
        video = tmp_path / "source.mp4"
        video.write_bytes(b"fake")
        sentences = _make_sentences(20)
        cache = CacheManager(base_dir=tmp_path / "cache")

        with (
            patch("core.pipeline._run_asr", new_callable=AsyncMock, return_value=sentences),
            patch("core.pipeline._run_director", new_callable=AsyncMock, return_value=[APPROVED_VERSION]),
            patch("core.pipeline._run_inspector", new_callable=AsyncMock, return_value=[]),
        ):
            config = _make_config(min_sentences=15)
            result = await process_video(video, config, cache=cache)

        assert result.success is False
        assert "质检" in result.error

    @pytest.mark.asyncio
    async def test_pipeline_exception_returns_failure(self, tmp_path):
        video = tmp_path / "source.mp4"
        video.write_bytes(b"fake")
        cache = CacheManager(base_dir=tmp_path / "cache")

        with patch("core.pipeline._run_asr", new_callable=AsyncMock, side_effect=RuntimeError("ASR boom")):
            config = _make_config(min_sentences=15)
            result = await process_video(video, config, cache=cache)

        assert result.success is False
        assert "ASR boom" in result.error
