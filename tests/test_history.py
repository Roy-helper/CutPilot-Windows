"""Tests for core.history — CRUD operations on history.json."""
import json
from unittest.mock import patch

from core.history import (
    HistoryEntry, add_history_entry, clear_history, delete_history_entry,
    load_history, save_history,
)


class TestHistoryEntry:
    def test_to_dict(self):
        entry = HistoryEntry(
            video_name="test.mp4", video_path="/path/test.mp4",
            timestamp="2026-01-01T00:00:00", success=True,
            versions_count=3, output_files=["/out/v1.mp4"],
            approach_tags=["痛点解决"], duration_sec=12.5,
        )
        d = entry.to_dict()
        assert d["video_name"] == "test.mp4"
        assert d["success"] is True
        assert d["versions_count"] == 3
        assert d["output_files"] == ["/out/v1.mp4"]
        assert d["duration_sec"] == 12.5

    def test_defaults(self):
        entry = HistoryEntry(
            video_name="x.mp4", video_path="/x.mp4",
            timestamp="t", success=False,
        )
        d = entry.to_dict()
        assert d["error"] == ""
        assert d["output_files"] == []
        assert d["approach_tags"] == []
        assert d["duration_sec"] == 0.0


class TestLoadHistory:
    def test_file_not_exists(self, tmp_path):
        fake_path = tmp_path / "no_such_file.json"
        with patch("core.history._HISTORY_PATH", fake_path):
            assert load_history() == []

    def test_valid_json_list(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text('[{"video_name": "a.mp4"}]', encoding="utf-8")
        with patch("core.history._HISTORY_PATH", path):
            result = load_history()
        assert len(result) == 1
        assert result[0]["video_name"] == "a.mp4"

    def test_json_not_list_returns_empty(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text('{"key": "value"}', encoding="utf-8")
        with patch("core.history._HISTORY_PATH", path):
            assert load_history() == []

    def test_corrupted_json_returns_empty(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text('not valid json!!!', encoding="utf-8")
        with patch("core.history._HISTORY_PATH", path):
            assert load_history() == []


class TestSaveHistory:
    def test_saves_json(self, tmp_path):
        path = tmp_path / "history.json"
        with patch("core.history._HISTORY_PATH", path):
            save_history([{"video_name": "a.mp4"}])
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == [{"video_name": "a.mp4"}]

    def test_trims_to_max_entries(self, tmp_path):
        path = tmp_path / "history.json"
        entries = [{"id": i} for i in range(600)]
        with patch("core.history._HISTORY_PATH", path):
            save_history(entries)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 500
        assert data[0]["id"] == 100  # trimmed from front


class TestAddHistoryEntry:
    def test_appends_entry(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text("[]", encoding="utf-8")
        entry = HistoryEntry(
            video_name="new.mp4", video_path="/new.mp4",
            timestamp="2026-01-01", success=True,
        )
        with patch("core.history._HISTORY_PATH", path):
            add_history_entry(entry)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["video_name"] == "new.mp4"


class TestClearHistory:
    def test_clears_all(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text('[{"a": 1}]', encoding="utf-8")
        with patch("core.history._HISTORY_PATH", path):
            clear_history()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == []


class TestDeleteHistoryEntry:
    def test_deletes_by_timestamp(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text(
            '[{"timestamp": "t1"}, {"timestamp": "t2"}]', encoding="utf-8",
        )
        with patch("core.history._HISTORY_PATH", path):
            delete_history_entry("t1")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["timestamp"] == "t2"

    def test_delete_nonexistent_is_noop(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text('[{"timestamp": "t1"}]', encoding="utf-8")
        with patch("core.history._HISTORY_PATH", path):
            delete_history_entry("nope")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1
