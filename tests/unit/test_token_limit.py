import pytest
from unittest.mock import MagicMock, patch
from src.ansari.agents.ansari import Ansari

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.MODEL = "gpt-4o"
    settings.MAX_TOKEN_LIMIT = 10
    settings.PROMPT_PATH = "/test/prompts"
    settings.SYSTEM_PROMPT_FILE_NAME = "system_msg_default"
    settings.KALEMAT_API_KEY.get_secret_value.return_value = "key"
    settings.VECTARA_API_KEY.get_secret_value.return_value = "key"
    settings.USUL_API_TOKEN.get_secret_value.return_value = "key"
    settings.MAWSUAH_VECTARA_CORPUS_KEY = "corpus"
    return settings

def test_token_limit_exceeded(mock_settings):
    with patch("src.ansari.agents.ansari.PromptMgr") as mock_prompt_mgr, \
         patch("src.ansari.agents.ansari.SearchQuran"), \
         patch("src.ansari.agents.ansari.SearchHadith"), \
         patch("src.ansari.agents.ansari.SearchMawsuah"), \
         patch("src.ansari.agents.ansari.SearchTafsirEncyc"), \
         patch("tiktoken.encoding_for_model") as mock_encoding:
        
        # Mock encoding to return a length > 10
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [1] * 20 # 20 tokens
        mock_encoding.return_value = mock_encoder

        mock_prompt = MagicMock()
        mock_prompt.render.return_value = "sys"
        mock_prompt_mgr.return_value.bind.return_value = mock_prompt

        ansari = Ansari(mock_settings)
        
        # Add a message
        ansari.message_history = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "This message is long enough."}
        ]
        
        # Process
        response_gen = ansari.process_message_history()
        response = next(response_gen)
        
        assert "The conversation has become too long" in response

def test_token_limit_not_exceeded(mock_settings):
    with patch("src.ansari.agents.ansari.PromptMgr") as mock_prompt_mgr, \
         patch("src.ansari.agents.ansari.SearchQuran"), \
         patch("src.ansari.agents.ansari.SearchHadith"), \
         patch("src.ansari.agents.ansari.SearchMawsuah"), \
         patch("src.ansari.agents.ansari.SearchTafsirEncyc"), \
         patch("tiktoken.encoding_for_model") as mock_encoding, \
         patch("src.ansari.agents.ansari.litellm.completion") as mock_completion:
        
        # Mock encoding to return a length < 10
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [1] * 5 # 5 tokens
        mock_encoding.return_value = mock_encoder

        mock_prompt = MagicMock()
        mock_prompt.render.return_value = "sys"
        mock_prompt_mgr.return_value.bind.return_value = mock_prompt

        # Mock completion response
        mock_chunk = MagicMock()
        mock_chunk.choices[0].delta.content = "Response"
        mock_chunk.choices[0].delta.tool_calls = None
        mock_completion.return_value = [mock_chunk]

        ansari = Ansari(mock_settings)
        
        # Add a short message
        ansari.message_history = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Short."}
        ]
        
        # Process
        response_gen = ansari.process_message_history()
        response = next(response_gen)
        
        assert response == "Response"
