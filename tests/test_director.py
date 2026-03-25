"""Tests for core.director — prompt building, JSON parsing, version generation."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.director import (
    _build_numbered_text,
    _extract_json,
    _load_category_preferences,
    _strip_think_tags,
    compute_version_duration,
    generate_versions,
    parse_json_versions,
)
from core.models import ScriptVersion, Sentence


# -- Fixtures ----------------------------------------------------------------


def _make_sentence(sid: int, start: float, end: float, text: str) -> Sentence:
    return Sentence(id=sid, start_sec=start, end_sec=end, text=text)


SAMPLE_SENTENCES = [
    _make_sentence(1, 0.0, 2.0, "你好"),
    _make_sentence(2, 2.0, 4.5, "这是测试"),
    _make_sentence(3, 4.5, 7.0, "谢谢观看"),
]


# -- _build_numbered_text ----------------------------------------------------


class TestBuildNumberedText:
    def test_simple_output(self):
        result = _build_numbered_text(SAMPLE_SENTENCES)
        assert result == "1. 你好\n2. 这是测试\n3. 谢谢观看"

    def test_empty_list(self):
        assert _build_numbered_text([]) == ""


# -- _extract_json -----------------------------------------------------------


class TestExtractJson:
    def test_plain_json(self):
        raw = '{"versions": [1, 2, 3]}'
        result = _extract_json(raw)
        assert result == {"versions": [1, 2, 3]}

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"key": "value"}\n```'
        result = _extract_json(raw)
        assert result == {"key": "value"}

    def test_json_with_plain_fences(self):
        raw = '```\n{"key": "value"}\n```'
        result = _extract_json(raw)
        assert result == {"key": "value"}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_json("not json at all")


# -- _strip_think_tags -------------------------------------------------------


class TestStripThinkTags:
    def test_with_think_tags(self):
        raw = "<think>reasoning here</think>actual content"
        assert _strip_think_tags(raw) == "actual content"

    def test_without_think_tags(self):
        raw = "just plain text"
        assert _strip_think_tags(raw) == "just plain text"

    def test_multiline_think(self):
        raw = "<think>\nline1\nline2\n</think>result"
        assert _strip_think_tags(raw) == "result"


# -- parse_json_versions -----------------------------------------------------


class TestParseJsonVersions:
    def test_valid_response(self):
        data = {
            "versions": [
                {
                    "version_id": 1,
                    "cover_title": "Title A",
                    "report": "Structure A",
                    "clip_order": [1, 2, 3],
                    "approach_tag": "痛点解决",
                    "publish_text": "文案A",
                    "cover_subtitle": "副标题A",
                    "tags": ["tag1", "tag2"],
                },
            ]
        }
        raw = json.dumps(data)
        versions = parse_json_versions(raw)
        assert len(versions) == 1
        v = versions[0]
        assert v.version_id == 1
        assert v.sentence_ids == [1, 2, 3]
        assert v.cover_title == "Title A"
        assert v.approach_tag == "痛点解决"
        assert v.tags == ["tag1", "tag2"]

    def test_empty_clip_order_skipped(self):
        data = {
            "versions": [
                {"version_id": 1, "clip_order": []},
                {"version_id": 2, "clip_order": [1, 2]},
            ]
        }
        versions = parse_json_versions(json.dumps(data))
        assert len(versions) == 1
        assert versions[0].sentence_ids == [1, 2]

    def test_no_versions_array_raises(self):
        with pytest.raises(ValueError, match="no 'versions' array"):
            parse_json_versions('{"other": 42}')

    def test_all_empty_clip_orders_raises(self):
        data = {"versions": [{"version_id": 1, "clip_order": []}]}
        with pytest.raises(ValueError, match="No valid versions"):
            parse_json_versions(json.dumps(data))

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_json_versions("not json {{{")


# -- compute_version_duration ------------------------------------------------


class TestComputeVersionDuration:
    def test_normal_case(self):
        version = ScriptVersion(version_id=1, sentence_ids=[1, 3])
        sentence_map = {s.id: s for s in SAMPLE_SENTENCES}
        duration = compute_version_duration(version, sentence_map)
        # sentence 1: 2.0-0.0=2.0, sentence 3: 7.0-4.5=2.5 => 4.5
        assert duration == 4.5

    def test_missing_sentence_ids_ignored(self):
        version = ScriptVersion(version_id=1, sentence_ids=[1, 99])
        sentence_map = {s.id: s for s in SAMPLE_SENTENCES}
        duration = compute_version_duration(version, sentence_map)
        assert duration == 2.0


# -- _load_category_preferences ----------------------------------------------


class TestLoadCategoryPreferences:
    def test_general_returns_empty(self):
        result = _load_category_preferences("general")
        assert result == ""

    def test_unknown_category_returns_empty(self):
        result = _load_category_preferences("nonexistent_category_xyz")
        assert result == ""

    @patch("core.director.get_prompts_dir")
    def test_known_category_returns_content(self, mock_dir, tmp_path):
        cat_dir = tmp_path / "categories"
        cat_dir.mkdir()
        cat_file = cat_dir / "beauty.md"
        cat_file.write_text("beauty preferences", encoding="utf-8")
        mock_dir.return_value = tmp_path

        result = _load_category_preferences("beauty")
        assert result == "beauty preferences"


# -- generate_versions (mocked LLM) -----------------------------------------


class TestGenerateVersions:
    @pytest.mark.asyncio
    async def test_full_flow_mocked(self):
        ai_response = json.dumps({
            "versions": [
                {
                    "version_id": 1,
                    "cover_title": "Title",
                    "report": "structure",
                    "clip_order": [1, 2],
                    "approach_tag": "痛点解决",
                    "publish_text": "text",
                    "cover_subtitle": "sub",
                    "tags": ["t1"],
                },
            ]
        })

        with (
            patch("core.director._call_llm", return_value=ai_response),
            patch("core.director._load_prompt_template", return_value="template {content_preferences}"),
            patch("core.director.detect_category", return_value="general"),
        ):
            config = MagicMock()
            config.model = "test-model"
            versions = await generate_versions(SAMPLE_SENTENCES, config, version_count=1)

        assert len(versions) == 1
        assert versions[0].sentence_ids == [1, 2]
        assert versions[0].estimated_duration > 0
