"""Tests for core.pipeline — full flow, error paths, cache hits, copy text."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.cache_manager import CacheManager
from core.models import ProcessResult, ScriptVersion, Sentence
from core.pipeline import generate_copy_text, process_video


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
