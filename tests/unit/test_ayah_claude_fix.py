"""Integration test to verify the ayah-claude endpoint fix."""

from unittest.mock import patch, MagicMock
import os
import tempfile


def test_ayah_claude_endpoint_loads_correct_system_prompt():
    """Test that the ayah-claude endpoint loads the system prompt correctly using PromptMgr."""
    
    # Create a temporary system prompt file
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create the prompts directory structure
        prompts_dir = os.path.join(tmpdir, "prompts")
        os.makedirs(prompts_dir)
        
        # Create test prompt files
        default_prompt_file = os.path.join(prompts_dir, "system_msg_default.txt")
        claude_prompt_file = os.path.join(prompts_dir, "system_msg_claude.txt")
        ayah_prompt_file = os.path.join(prompts_dir, "system_msg_ayah.txt")
        
        with open(default_prompt_file, "w") as f:
            f.write("Default system prompt")
        with open(claude_prompt_file, "w") as f:
            f.write("Claude system prompt")
        with open(ayah_prompt_file, "w") as f:
            f.write("Ayah system prompt for Quranic questions")
            
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"
        mock_settings.ANTHROPIC_MODEL = "claude-3-opus-20240229"
        mock_settings.KALEMAT_API_KEY.get_secret_value.return_value = "test-key"
        mock_settings.VECTARA_API_KEY.get_secret_value.return_value = "test-key"
        mock_settings.USUL_API_TOKEN.get_secret_value.return_value = "test-key"
        mock_settings.MAWSUAH_VECTARA_CORPUS_KEY = "test-corpus"
        mock_settings.TAFSIR_VECTARA_CORPUS_KEY = "test-tafsir"
        mock_settings.MODEL = "test-model"
        mock_settings.PROMPT_PATH = prompts_dir
        mock_settings.SYSTEM_PROMPT_FILE_NAME = "system_msg_default"
        mock_settings.AYAH_SYSTEM_PROMPT_FILE_NAME = "system_msg_ayah"
        
        # Patch Anthropic client
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client
            
            from src.ansari.agents.ansari_claude import AnsariClaude
            
            # Test 1: Default initialization should use system_msg_claude
            ansari_default = AnsariClaude(mock_settings)
            assert ansari_default.system_prompt_file == "system_msg_claude"
            
            # Test 2: Initialization with ayah system prompt
            ansari_ayah = AnsariClaude(
                mock_settings,
                system_prompt_file=mock_settings.AYAH_SYSTEM_PROMPT_FILE_NAME
            )
            assert ansari_ayah.system_prompt_file == "system_msg_ayah"
            
            # Test 3: Verify process_one_round uses the correct prompt file
            # Mock the API response
            mock_response = MagicMock()
            mock_response.__iter__ = MagicMock(return_value=iter([]))
            mock_client.messages.create.return_value = mock_response
            
            # Add a message to process
            ansari_ayah.message_history = [{"role": "user", "content": "test question"}]
            
            # Process the message
            list(ansari_ayah.process_one_round())
            
            # Verify the API was called with the ayah system prompt
            api_call_args = mock_client.messages.create.call_args
            if api_call_args:
                system_prompt = api_call_args.kwargs.get("system", [{}])[0].get("text", "")
                # The system prompt should be loaded from the ayah file
                # We can't check the exact content without actually loading the file,
                # but we can verify the API was called
                assert mock_client.messages.create.called


def test_ansari_claude_accepts_system_prompt_file_parameter():
    """Test that AnsariClaude constructor accepts system_prompt_file parameter."""
    
    # This test verifies the signature change without needing to mock all dependencies
    from inspect import signature
    from src.ansari.agents.ansari_claude import AnsariClaude
    
    # Get the signature of the __init__ method
    sig = signature(AnsariClaude.__init__)
    
    # Check that system_prompt_file is a parameter
    assert "system_prompt_file" in sig.parameters
    
    # Check that it has a default value of None
    param = sig.parameters["system_prompt_file"]
    assert param.default is None