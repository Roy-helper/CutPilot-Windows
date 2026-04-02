"""Tests for core.ai_client — OpenAI client creation and call_ai."""
from unittest.mock import MagicMock, patch

from core.ai_client import call_ai, create_openai_client
from core.config import CutPilotConfig


class TestCreateOpenaiClient:
    def test_uses_config_values(self):
        config = CutPilotConfig(api_key="test-key", base_url="https://test.com/v1")
        client = create_openai_client(config)
        assert client.api_key == "test-key"

    def test_none_config_uses_defaults(self):
        client = create_openai_client(None)
        assert client is not None


class TestCallAi:
    def test_strips_think_tags(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "<think>internal reasoning</think>The actual answer"
        )

        with patch("core.ai_client.create_openai_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            result = call_ai("test prompt", config=CutPilotConfig(api_key="k"))

        assert "think" not in result
        assert result == "The actual answer"

    def test_system_message_included(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"

        with patch("core.ai_client.create_openai_client") as mock_client:
            mock_create = mock_client.return_value.chat.completions.create
            mock_create.return_value = mock_response
            call_ai("prompt", system="you are helpful", config=CutPilotConfig(api_key="k"))

        messages = mock_create.call_args[1]["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_no_system_message(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"

        with patch("core.ai_client.create_openai_client") as mock_client:
            mock_create = mock_client.return_value.chat.completions.create
            mock_create.return_value = mock_response
            call_ai("prompt", system="", config=CutPilotConfig(api_key="k"))

        messages = mock_create.call_args[1]["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_none_content_returns_empty(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        with patch("core.ai_client.create_openai_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            result = call_ai("prompt", config=CutPilotConfig(api_key="k"))

        assert result == ""
