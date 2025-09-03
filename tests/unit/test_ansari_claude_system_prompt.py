"""Unit tests for AnsariClaude system_prompt_file parameter."""

import pytest
from unittest.mock import MagicMock, patch, mock_open
import anthropic


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = MagicMock()
    settings.ANTHROPIC_API_KEY = MagicMock()
    settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-api-key"
    settings.ANTHROPIC_MODEL = "claude-3-opus-20240229"
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
    return settings


class TestAnsariClaudeSystemPrompt:
    """Test AnsariClaude system prompt file parameter."""

    def test_default_system_prompt_file(self, mock_settings):
        """Test that AnsariClaude uses default system prompt file when not specified."""
        with patch("anthropic.Anthropic"), \
             patch("src.ansari.util.prompt_mgr.PromptMgr") as mock_prompt_mgr:
            # Mock the prompt manager
            mock_prompt = MagicMock()
            mock_prompt.render.return_value = "Test system prompt"
            mock_prompt_mgr.return_value.bind.return_value = mock_prompt
            
            from src.ansari.agents.ansari_claude import AnsariClaude
            
            # Initialize without system_prompt_file parameter
            ansari = AnsariClaude(mock_settings)
            
            # Verify default is used
            assert ansari.system_prompt_file == "system_msg_claude"

    def test_custom_system_prompt_file(self, mock_settings):
        """Test that AnsariClaude uses custom system prompt file when specified."""
        with patch("anthropic.Anthropic"), \
             patch("src.ansari.util.prompt_mgr.PromptMgr") as mock_prompt_mgr:
            # Mock the prompt manager
            mock_prompt = MagicMock()
            mock_prompt.render.return_value = "Test system prompt"
            mock_prompt_mgr.return_value.bind.return_value = mock_prompt
            
            from src.ansari.agents.ansari_claude import AnsariClaude
            
            # Initialize with custom system_prompt_file
            ansari = AnsariClaude(mock_settings, system_prompt_file="system_msg_ayah")
            
            # Verify custom file is used
            assert ansari.system_prompt_file == "system_msg_ayah"

    def test_system_prompt_loaded_in_process_one_round(self, mock_settings):
        """Test that the correct system prompt file is loaded during process_one_round."""
        with patch("anthropic.Anthropic") as mock_anthropic:
            # Mock the Anthropic client
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client
            
            # Mock the response stream
            mock_response = MagicMock()
            mock_response.__iter__ = MagicMock(return_value=iter([]))
            mock_client.messages.create.return_value = mock_response
            
            from src.ansari.agents.ansari_claude import AnsariClaude
            from src.ansari.util.prompt_mgr import PromptMgr
            
            # Initialize with custom system prompt file
            ansari = AnsariClaude(mock_settings, system_prompt_file="system_msg_ayah")
            
            # Add a message to history
            ansari.message_history = [{"role": "user", "content": "test question"}]
            
            # Mock PromptMgr to verify the correct file is loaded
            with patch.object(PromptMgr, 'bind') as mock_bind:
                mock_prompt = MagicMock()
                mock_prompt.render.return_value = "Test ayah system prompt"
                mock_bind.return_value = mock_prompt
                
                # Call process_one_round
                result = list(ansari.process_one_round())
                
                # Verify the correct system prompt file was loaded
                mock_bind.assert_called_with("system_msg_ayah")

    def test_ayah_endpoint_initialization(self, mock_settings):
        """Test that the ayah-claude endpoint can initialize AnsariClaude with custom system prompt."""
        with patch("anthropic.Anthropic"):
            from src.ansari.agents.ansari_claude import AnsariClaude
            
            # Simulate ayah endpoint initialization
            ansari = AnsariClaude(
                mock_settings,
                system_prompt_file=mock_settings.AYAH_SYSTEM_PROMPT_FILE_NAME
            )
            
            # Verify the ayah system prompt file is used
            assert ansari.system_prompt_file == "system_msg_ayah"

    def test_process_one_round_with_different_prompts(self, mock_settings):
        """Test that different system prompts are used based on initialization."""
        with patch("anthropic.Anthropic") as mock_anthropic:
            # Mock the Anthropic client
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client
            
            # Mock the response stream
            mock_response = MagicMock()
            mock_response.__iter__ = MagicMock(return_value=iter([]))
            mock_client.messages.create.return_value = mock_response
            
            from src.ansari.agents.ansari_claude import AnsariClaude
            from src.ansari.util.prompt_mgr import PromptMgr
            
            # Test with default prompt
            ansari_default = AnsariClaude(mock_settings)
            ansari_default.message_history = [{"role": "user", "content": "test"}]
            
            with patch.object(PromptMgr, 'bind') as mock_bind:
                mock_prompt = MagicMock()
                mock_prompt.render.return_value = "Default system prompt"
                mock_bind.return_value = mock_prompt
                
                list(ansari_default.process_one_round())
                mock_bind.assert_called_with("system_msg_claude")
            
            # Test with ayah prompt
            ansari_ayah = AnsariClaude(mock_settings, system_prompt_file="system_msg_ayah")
            ansari_ayah.message_history = [{"role": "user", "content": "test"}]
            
            with patch.object(PromptMgr, 'bind') as mock_bind:
                mock_prompt = MagicMock()
                mock_prompt.render.return_value = "Ayah system prompt"
                mock_bind.return_value = mock_prompt
                
                list(ansari_ayah.process_one_round())
                mock_bind.assert_called_with("system_msg_ayah")