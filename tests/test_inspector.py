"""Tests for core.inspector — word scanning, overlap, scoring, review."""
import json
from unittest.mock import patch

import pytest

from core.inspector import (
    _compute_weighted_score,
    _decide_version,
    check_prohibited_words,
    compute_overlap_matrix,
    compute_overlap_ratio,
    detect_overlap_groups,
    extract_core_hook_text,
    load_sensitive_words,
    review_versions,
)
from core.models import ScriptVersion, Sentence


# -- Fixtures ----------------------------------------------------------------


def _s(sid: int, start: float, end: float, text: str) -> Sentence:
    return Sentence(id=sid, start_sec=start, end_sec=end, text=text)


def _v(vid: int, sids: list[int], **kwargs) -> ScriptVersion:
    return ScriptVersion(version_id=vid, sentence_ids=sids, **kwargs)


SENTENCES = [
    _s(1, 0.0, 2.0, "开头"),
    _s(2, 2.0, 4.0, "中间"),
    _s(3, 4.0, 6.0, "结尾"),
    _s(4, 6.0, 8.0, "额外"),
    _s(5, 8.0, 10.0, "最后"),
]


# -- load_sensitive_words ----------------------------------------------------


class TestLoadSensitiveWords:
    def test_file_exists(self, tmp_path):
        data = {"prohibited": ["坏词"], "sensitive": ["敏感"], "platform_risk": []}
        path = tmp_path / "words.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        result = load_sensitive_words(path)
        assert result["prohibited"] == ["坏词"]
        assert result["sensitive"] == ["敏感"]

    def test_file_missing_returns_fallback(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        result = load_sensitive_words(path)
        assert result == {"prohibited": [], "sensitive": [], "platform_risk": []}


# -- check_prohibited_words --------------------------------------------------


class TestCheckProhibitedWords:
    def test_hits(self):
        words = {"prohibited": ["坏词"], "sensitive": ["敏感"], "platform_risk": ["风险"]}
        prohibited, sensitive = check_prohibited_words("这里有坏词和敏感内容还有风险", words)
        assert prohibited == ["坏词"]
        assert "敏感" in sensitive
        assert "风险" in sensitive

    def test_misses(self):
        words = {"prohibited": ["坏词"], "sensitive": ["敏感"], "platform_risk": []}
        prohibited, sensitive = check_prohibited_words("干净的文本", words)
        assert prohibited == []
        assert sensitive == []


# -- compute_overlap_ratio ---------------------------------------------------


class TestComputeOverlapRatio:
    def test_full_overlap(self):
        assert compute_overlap_ratio([1, 2, 3], [1, 2, 3]) == 1.0

    def test_no_overlap(self):
        assert compute_overlap_ratio([1, 2], [3, 4]) == 0.0

    def test_partial_overlap(self):
        # intersection={2}, min(2,3)=2 => 0.5
        ratio = compute_overlap_ratio([1, 2], [2, 3, 4])
        assert ratio == 0.5

    def test_empty_a(self):
        assert compute_overlap_ratio([], [1, 2]) == 0.0

    def test_empty_b(self):
        assert compute_overlap_ratio([1, 2], []) == 0.0

    def test_both_empty(self):
        assert compute_overlap_ratio([], []) == 0.0


# -- compute_overlap_matrix --------------------------------------------------


class TestComputeOverlapMatrix:
    def test_multiple_versions(self):
        v1 = _v(1, [1, 2, 3])
        v2 = _v(2, [2, 3, 4])
        v3 = _v(3, [5])
        matrix = compute_overlap_matrix([v1, v2, v3])
        assert (1, 2) in matrix
        assert (1, 3) in matrix
        assert (2, 3) in matrix
        # v1 vs v2: intersection={2,3}, min(3,3)=3 => 2/3
        assert abs(matrix[(1, 2)] - 2 / 3) < 0.01


# -- detect_overlap_groups ---------------------------------------------------


class TestDetectOverlapGroups:
    def test_grouping_above_threshold(self):
        v1 = _v(1, [1, 2, 3])
        v2 = _v(2, [1, 2, 3])  # 100% overlap with v1
        v3 = _v(3, [4, 5])  # no overlap
        groups = detect_overlap_groups([v1, v2, v3], threshold=0.5)
        assert groups[1] == groups[2]
        assert 3 not in groups

    def test_no_groups_below_threshold(self):
        v1 = _v(1, [1, 2, 3])
        v2 = _v(2, [4, 5, 6])
        groups = detect_overlap_groups([v1, v2], threshold=0.5)
        assert groups == {}


# -- extract_core_hook_text --------------------------------------------------


class TestExtractCoreHookText:
    def test_normal_case(self):
        version = _v(1, [1, 2, 3])
        sentence_map = {s.id: s for s in SENTENCES}
        text = extract_core_hook_text(version, sentence_map, max_seconds=5.0)
        # s1: 0-2, s2: 2-4, s3: 4-6 => s3.start-s1.start=4 < 5, include all 3
        assert text == "开头中间结尾"

    def test_max_seconds_limit(self):
        version = _v(1, [1, 2, 3])
        sentence_map = {s.id: s for s in SENTENCES}
        text = extract_core_hook_text(version, sentence_map, max_seconds=3.0)
        # s1: start=0, s2: start=2 (2-0=2<3 include), s3: start=4 (4-0=4>=3 stop)
        assert text == "开头中间"


# -- _compute_weighted_score -------------------------------------------------


class TestComputeWeightedScore:
    def test_verify_formula(self):
        dims = {
            "hook_strength": 80,
            "coherence": 70,
            "structure": 60,
            "differentiation": 90,
            "commercial_value": 50,
        }
        # (80 + 70 + 60 + 90*1.5 + 50) / 5.5 = (80+70+60+135+50)/5.5 = 395/5.5
        expected = round(395 / 5.5, 1)
        assert _compute_weighted_score(dims) == expected

    def test_defaults_to_60(self):
        score = _compute_weighted_score({})
        # (60 + 60 + 60 + 60*1.5 + 60) / 5.5 = (60+60+60+90+60)/5.5 = 330/5.5 = 60.0
        assert score == 60.0


# -- _decide_version --------------------------------------------------------


class TestDecideVersion:
    def test_prohibited_rejects(self):
        result = _decide_version(ai_decision="approved", score=80.0, prohibited=["坏词"])
        assert result == "rejected"

    def test_low_score_rejects(self):
        result = _decide_version(ai_decision="approved", score=30.0, prohibited=[])
        assert result == "rejected"

    def test_ai_rejected(self):
        result = _decide_version(ai_decision="rejected", score=80.0, prohibited=[])
        assert result == "rejected"

    def test_approved(self):
        result = _decide_version(ai_decision="approved", score=80.0, prohibited=[])
        assert result == "approved"


# -- review_versions (mocked AI) --------------------------------------------


class TestReviewVersions:
    @pytest.mark.asyncio
    async def test_returns_approved_list(self):
        versions = [_v(1, [1, 2], title="V1"), _v(2, [3, 4], title="V2")]
        ai_response = json.dumps({
            "reviews": [
                {"version_id": 1, "decision": "approved", "score": 80, "dimensions": {}},
                {"version_id": 2, "decision": "rejected", "score": 30, "dimensions": {}},
            ]
        })

        with (
            patch("core.inspector.load_sensitive_words", return_value={
                "prohibited": [], "sensitive": [], "platform_risk": [],
            }),
            patch("core.inspector.call_ai", return_value=ai_response),
            patch("core.inspector._load_system_prompt", return_value="prompt"),
        ):
            from core.config import CutPilotConfig

            config = CutPilotConfig(api_key="test")
            approved = await review_versions(versions, SENTENCES, config)

        # V1 approved (score=80), V2 rejected by AI but fallback may apply
        # V2 score=30 < 50 so it's rejected; V1 is approved
        assert len(approved) >= 1
        assert any(v.version_id == 1 for v in approved)
