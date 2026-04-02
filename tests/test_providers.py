"""Tests for core.providers — provider preset lookup."""
from core.providers import PROVIDERS, ProviderPreset, get_provider, get_provider_names


class TestProviderPreset:
    def test_frozen(self):
        p = PROVIDERS[0]
        import pytest
        with pytest.raises(Exception):
            p.id = "changed"

    def test_deepseek_is_first(self):
        assert PROVIDERS[0].id == "deepseek"


class TestGetProvider:
    def test_found(self):
        p = get_provider("deepseek")
        assert p is not None
        assert p.name == "DeepSeek"
        assert "deepseek" in p.base_url

    def test_not_found(self):
        assert get_provider("nonexistent") is None

    def test_custom_provider(self):
        p = get_provider("custom")
        assert p is not None
        assert p.base_url == ""


class TestGetProviderNames:
    def test_returns_all(self):
        names = get_provider_names()
        assert len(names) == len(PROVIDERS)
        ids = [n[0] for n in names]
        assert "deepseek" in ids
        assert "custom" in ids

    def test_tuple_format(self):
        names = get_provider_names()
        for item in names:
            assert len(item) == 2
            assert isinstance(item[0], str)
            assert isinstance(item[1], str)
