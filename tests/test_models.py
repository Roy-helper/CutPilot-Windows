"""Tests for core.models — immutability, validators, defaults."""
import pytest
from pydantic import ValidationError

from core.models import (
    APPROACH_TAGS,
    PipelineState,
    ProcessResult,
    ScriptVersion,
    Sentence,
)


# -- Sentence ----------------------------------------------------------------


class TestSentence:
    def test_create_with_required_fields(self):
        s = Sentence(id=1, start_sec=0.0, end_sec=1.5, text="hello")
        assert s.id == 1
        assert s.text == "hello"

    def test_default_optional_fields(self):
        s = Sentence(id=1, start_sec=0.0, end_sec=1.0, text="x")
        assert s.speaker_id is None
        assert s.confidence is None

    def test_frozen_raises_on_mutation(self):
        s = Sentence(id=1, start_sec=0.0, end_sec=1.0, text="x")
        with pytest.raises(ValidationError):
            s.text = "changed"


# -- ScriptVersion -----------------------------------------------------------


class TestScriptVersion:
    def test_defaults(self):
        v = ScriptVersion(version_id=1)
        assert v.title == ""
        assert v.sentence_ids == []
        assert v.score == 0.0
        assert v.tags == []
        assert v.approach_tag == ""

    def test_frozen_raises_on_mutation(self):
        v = ScriptVersion(version_id=1, title="test")
        with pytest.raises(ValidationError):
            v.title = "changed"

    def test_valid_approach_tag_passes(self):
        for tag in APPROACH_TAGS:
            v = ScriptVersion(version_id=1, approach_tag=tag)
            assert v.approach_tag == tag

    def test_invalid_approach_tag_becomes_empty(self):
        v = ScriptVersion(version_id=1, approach_tag="invalid_tag")
        assert v.approach_tag == ""

    def test_empty_approach_tag_passes(self):
        v = ScriptVersion(version_id=1, approach_tag="")
        assert v.approach_tag == ""


# -- ProcessResult -----------------------------------------------------------


class TestProcessResult:
    def test_defaults(self):
        r = ProcessResult(success=True)
        assert r.error == ""
        assert r.versions == []
        assert r.output_files == []

    def test_frozen_raises_on_mutation(self):
        r = ProcessResult(success=True)
        with pytest.raises(ValidationError):
            r.success = False


# -- PipelineState -----------------------------------------------------------


class TestPipelineState:
    def test_defaults(self):
        p = PipelineState(video_path="/tmp/test.mp4")
        assert p.asr_done is False
        assert p.director_done is False
        assert p.inspector_done is False
        assert p.editor_done is False

    def test_frozen_raises_on_mutation(self):
        p = PipelineState(video_path="/tmp/test.mp4")
        with pytest.raises(ValidationError):
            p.asr_done = True
