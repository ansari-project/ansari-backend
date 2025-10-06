"""Unit tests for AnsariClaude model version verification."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = MagicMock()
    settings.ANTHROPIC_API_KEY = MagicMock()
    settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-api-key"
    settings.ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"
    settings.KALEMAT_API_KEY = MagicMock()
    settings.KALEMAT_API_KEY.get_secret_value.return_value = "test-kalemat-key"
    settings.VECTARA_API_KEY = MagicMock()
    settings.VECTARA_API_KEY.get_secret_value.return_value = "test-vectara-key"
    settings.MAWSUAH_VECTARA_CORPUS_KEY = "test-corpus-key"
    settings.TAFSIR_VECTARA_CORPUS_KEY = "test-tafsir-key"
    settings.USUL_API_TOKEN = MagicMock()
    settings.USUL_API_TOKEN.get_secret_value.return_value = "test-usul-token"
    settings.MODEL = "test-model"
    settings.PROMPT_PATH = "/test/prompts"
    settings.SYSTEM_PROMPT_FILE_NAME = "system_msg_default"
    settings.AYAH_SYSTEM_PROMPT_FILE_NAME = "system_msg_ayah"
    settings.MAX_FAILURES = 3
    return settings


class TestAnsariClaudeModelVersion:
    """Test AnsariClaude model version configuration."""

    def test_model_version_is_sonnet_4_5(self, mock_settings):
        """Test that AnsariClaude uses Sonnet 4.5 model."""
        with patch("anthropic.Anthropic"), patch("ansari.agents.ansari.PromptMgr") as mock_prompt_mgr:
            # Mock the prompt manager
            mock_prompt = MagicMock()
            mock_prompt.render.return_value = "Test system prompt"
            mock_prompt_mgr.return_value.bind.return_value = mock_prompt

            from src.ansari.agents.ansari_claude import AnsariClaude

            # Initialize AnsariClaude
            ansari = AnsariClaude(mock_settings)

            # Verify the model version is Sonnet 4.5
            assert ansari.settings.ANTHROPIC_MODEL == "claude-sonnet-4-5-20250929"

    def test_model_sent_to_api(self, mock_settings):
        """Test that the correct model version is sent to the Anthropic API."""
        with patch("anthropic.Anthropic") as mock_anthropic, patch("ansari.agents.ansari.PromptMgr") as mock_prompt_mgr:
            # Mock the prompt manager
            mock_prompt = MagicMock()
            mock_prompt.render.return_value = "Test system prompt"
            mock_prompt_mgr.return_value.bind.return_value = mock_prompt

            # Mock the Anthropic client
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            # Mock the response stream
            mock_response = MagicMock()
            mock_response.__iter__ = MagicMock(return_value=iter([]))
            mock_client.messages.create.return_value = mock_response

            from src.ansari.agents.ansari_claude import AnsariClaude

            # Initialize AnsariClaude
            ansari = AnsariClaude(mock_settings)

            # Add a message to history
            ansari.message_history = [{"role": "user", "content": "test question"}]

            # Call process_one_round to trigger API call
            list(ansari.process_one_round())

            # Verify the correct model was sent to the API
            mock_client.messages.create.assert_called_once()
            call_args = mock_client.messages.create.call_args
            assert call_args[1]["model"] == "claude-sonnet-4-5-20250929"

    def test_default_config_uses_sonnet_4_5(self):
        """Test that the default configuration in Settings uses Sonnet 4.5."""
        from src.ansari.config import Settings

        # Create settings with defaults (no overrides)
        settings = Settings(
            OPENAI_API_KEY="test-key",
            ANTHROPIC_API_KEY="test-key",
            KALEMAT_API_KEY="test-key",
            VECTARA_API_KEY="test-key",
            QURAN_DOT_COM_API_KEY="test-key",
        )

        # Verify the default model is Sonnet 4.5
        assert settings.ANTHROPIC_MODEL == "claude-sonnet-4-5-20250929"
