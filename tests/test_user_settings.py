"""Tests for core.user_settings — load/save/build config."""
import json
from unittest.mock import MagicMock, patch

from core.user_settings import build_config_from_settings, load_user_settings, save_user_settings


class TestLoadUserSettings:
    def test_no_file_returns_defaults(self, tmp_path):
        fake_path = tmp_path / "settings.json"
        with patch("core.user_settings._SETTINGS_PATH", fake_path):
            settings = load_user_settings()
        assert settings["provider"] == "deepseek"
        assert settings["max_versions"] == 3
        assert settings["_settings_corrupted"] is False

    def test_valid_json_overrides(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text('{"provider": "qwen", "max_versions": 5}', encoding="utf-8")
        with patch("core.user_settings._SETTINGS_PATH", path):
            settings = load_user_settings()
        assert settings["provider"] == "qwen"
        assert settings["max_versions"] == 5
        # Defaults for unset keys
        assert settings["generate_fast"] is True

    def test_json_not_dict_marks_corrupted(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with patch("core.user_settings._SETTINGS_PATH", path):
            settings = load_user_settings()
        assert settings["_settings_corrupted"] is True
        assert settings["provider"] == "deepseek"  # defaults

    def test_invalid_json_marks_corrupted(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("not json!!!", encoding="utf-8")
        with patch("core.user_settings._SETTINGS_PATH", path):
            settings = load_user_settings()
        assert settings["_settings_corrupted"] is True


class TestSaveUserSettings:
    def test_saves_only_known_keys(self, tmp_path):
        path = tmp_path / "settings.json"
        settings_dir = tmp_path
        with (
            patch("core.user_settings._SETTINGS_PATH", path),
            patch("core.user_settings._SETTINGS_DIR", settings_dir),
        ):
            save_user_settings({
                "provider": "kimi",
                "unknown_key": "should_be_filtered",
                "max_versions": 5,
            })
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["provider"] == "kimi"
        assert data["max_versions"] == 5
        assert "unknown_key" not in data

    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "sub" / "dir"
        path = nested / "settings.json"
        with (
            patch("core.user_settings._SETTINGS_PATH", path),
            patch("core.user_settings._SETTINGS_DIR", nested),
        ):
            save_user_settings({"provider": "deepseek"})
        assert path.exists()


class TestBuildConfigFromSettings:
    def test_uses_provider_preset(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text('{"provider": "qwen", "api_key": "test-key"}', encoding="utf-8")
        with patch("core.user_settings._SETTINGS_PATH", path):
            config = build_config_from_settings()
        assert config.api_key == "test-key"
        assert "dashscope" in config.base_url  # qwen preset

    def test_custom_provider_uses_user_url(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(
            '{"provider": "custom", "api_key": "k", "base_url": "https://my.api/v1", "model": "my-model"}',
            encoding="utf-8",
        )
        with patch("core.user_settings._SETTINGS_PATH", path):
            config = build_config_from_settings()
        assert config.base_url == "https://my.api/v1"
        assert config.model == "my-model"

    def test_no_api_key_tries_builtin(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text('{"provider": "deepseek"}', encoding="utf-8")
        with (
            patch("core.user_settings._SETTINGS_PATH", path),
            patch.dict("sys.modules", {"core.builtin_keys": MagicMock(
                DEEPSEEK_API_KEY="builtin-key",
                DEEPSEEK_BASE_URL="https://builtin.api/v1",
                DEEPSEEK_MODEL="builtin-model",
            )}),
        ):
            config = build_config_from_settings()
        assert config.api_key == "builtin-key"
