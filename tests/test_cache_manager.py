"""Tests for core.cache_manager — save/load/clear/exists."""
import pytest

from core.cache_manager import CacheManager


# -- Fixtures ----------------------------------------------------------------


@pytest.fixture
def cache(tmp_path):
    return CacheManager(base_dir=tmp_path / "cache")


@pytest.fixture
def video_file(tmp_path):
    """Create a dummy video file so _cache_path can stat it."""
    vf = tmp_path / "test_video.mp4"
    vf.write_bytes(b"fake video content 1234")
    return vf


# -- exists ------------------------------------------------------------------


class TestExists:
    def test_false_when_no_cache(self, cache, video_file):
        assert cache.exists(video_file, "asr") is False

    def test_true_after_save(self, cache, video_file):
        cache.save(video_file, "asr", {"sentences": [1, 2, 3]})
        assert cache.exists(video_file, "asr") is True


# -- save + load roundtrip ---------------------------------------------------


class TestSaveLoad:
    def test_roundtrip_dict(self, cache, video_file):
        data = {"key": "value", "nested": {"a": 1}}
        cache.save(video_file, "director", data)
        loaded = cache.load(video_file, "director")
        assert loaded == data

    def test_roundtrip_list(self, cache, video_file):
        data = [{"id": 1}, {"id": 2}]
        cache.save(video_file, "inspector", data)
        loaded = cache.load(video_file, "inspector")
        assert loaded == data

    def test_load_nonexistent_raises(self, cache, video_file):
        with pytest.raises(FileNotFoundError):
            cache.load(video_file, "nonexistent_stage")


# -- clear -------------------------------------------------------------------


class TestClear:
    def test_removes_video_cache(self, cache, video_file):
        cache.save(video_file, "asr", [1, 2])
        cache.save(video_file, "director", [3, 4])
        assert cache.exists(video_file, "asr") is True

        cache.clear(video_file)
        assert cache.exists(video_file, "asr") is False
        assert cache.exists(video_file, "director") is False


# -- clear_all ---------------------------------------------------------------


class TestClearAll:
    def test_removes_everything(self, cache, video_file, tmp_path):
        cache.save(video_file, "asr", [1])

        other_video = tmp_path / "other.mp4"
        other_video.write_bytes(b"other video")
        cache.save(other_video, "asr", [2])

        cache.clear_all()
        assert not cache.base_dir.exists()


# -- _cache_path determinism -------------------------------------------------


class TestCachePath:
    def test_deterministic_for_same_input(self, cache, video_file):
        path1 = cache._cache_path(video_file, "asr")
        path2 = cache._cache_path(video_file, "asr")
        assert path1 == path2

    def test_different_stages_same_parent(self, cache, video_file):
        path_asr = cache._cache_path(video_file, "asr")
        path_dir = cache._cache_path(video_file, "director")
        assert path_asr.parent == path_dir.parent
        assert path_asr.name == "asr.json"
        assert path_dir.name == "director.json"
