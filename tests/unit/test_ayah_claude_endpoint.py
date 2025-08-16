"""Unit tests for the /api/v2/ayah-claude endpoint."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, mock_open
import json


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from src.ansari.app.main_api import app
    return TestClient(app)


@pytest.fixture
def mock_settings():
    """Mock settings with test API key."""
    with patch("src.ansari.app.main_api.get_settings") as mock:
        settings = MagicMock()
        settings.QURAN_DOT_COM_API_KEY.get_secret_value.return_value = "test-api-key"
        settings.AYAH_SYSTEM_PROMPT_FILE_NAME = "ayah_system_prompt.md"
        settings.MONGO_URL = "mongodb://test:27017"
        settings.MONGO_DB_NAME = "test_db"
        mock.return_value = settings
        yield settings


@pytest.fixture  
def mock_db():
    """Mock database for testing."""
    with patch("src.ansari.app.main_api.AnsariDB") as mock_class:
        db_instance = MagicMock()
        db_instance.get_quran_answer = MagicMock()
        db_instance.store_quran_answer = MagicMock()
        mock_class.return_value = db_instance
        yield db_instance


@pytest.fixture
def mock_ansari_claude():
    """Mock AnsariClaude for testing."""
    with patch("src.ansari.app.main_api.AnsariClaude") as mock:
        instance = MagicMock()
        # Mock the generator response
        def mock_generator():
            yield "This is a test response "
            yield "about the ayah "
            yield "with citations."
        instance.replace_message_history.return_value = mock_generator()
        mock.return_value = instance
        yield mock


class TestAyahClaudeEndpoint:
    """Test cases for the /api/v2/ayah-claude endpoint."""

    def test_endpoint_exists(self, client):
        """Test that the endpoint is registered."""
        response = client.post(
            "/api/v2/ayah-claude",
            json={
                "surah": 1,
                "ayah": 1,
                "question": "What is the meaning?",
                "apikey": "wrong-key"
            }
        )
        # Should not return 404
        assert response.status_code != 404

    def test_authentication_required(self, client, mock_settings):
        """Test that API key authentication is enforced."""
        # Test with wrong API key
        response = client.post(
            "/api/v2/ayah-claude",
            json={
                "surah": 1,
                "ayah": 1,
                "question": "What is the meaning?",
                "apikey": "wrong-api-key"
            }
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"

    def test_successful_request_with_valid_key(self, client, mock_settings, mock_db, mock_ansari_claude):
        """Test successful request with valid API key."""
        # Mock the file reading for system prompt
        with patch("builtins.open", mock_open(read_data="Test system prompt")):
            # Mock that no cached answer exists
            mock_db.get_quran_answer.return_value = None
            
            response = client.post(
                "/api/v2/ayah-claude",
                json={
                    "surah": 1,
                    "ayah": 1,
                    "question": "What is the meaning?",
                    "apikey": "test-api-key",
                    "use_cache": True
                }
            )
            
            assert response.status_code == 200
            assert "response" in response.json()
            assert response.json()["response"] == "This is a test response about the ayah with citations."

    def test_cache_retrieval(self, client, mock_settings, mock_db):
        """Test that cached answers are returned when available."""
        # Mock a cached answer
        cached_answer = "This is a cached response"
        mock_db.get_quran_answer.return_value = cached_answer
        
        response = client.post(
            "/api/v2/ayah-claude",
            json={
                "surah": 1,
                "ayah": 1,
                "question": "What is the meaning?",
                "apikey": "test-api-key",
                "use_cache": True
            }
        )
        
        assert response.status_code == 200
        assert response.json()["response"] == cached_answer
        # Verify that get_quran_answer was called
        mock_db.get_quran_answer.assert_called_once_with(1, 1, "What is the meaning?")

    def test_cache_disabled(self, client, mock_settings, mock_db, mock_ansari_claude):
        """Test that cache is bypassed when use_cache is False."""
        with patch("builtins.open", mock_open(read_data="Test system prompt")):
            # Even if cache has an answer, it shouldn't be used
            mock_db.get_quran_answer.return_value = "Cached answer"
            
            response = client.post(
                "/api/v2/ayah-claude",
                json={
                    "surah": 2,
                    "ayah": 255,
                    "question": "Explain this verse",
                    "apikey": "test-api-key",
                    "use_cache": False
                }
            )
            
            assert response.status_code == 200
            # Should not return cached answer
            assert response.json()["response"] != "Cached answer"
            # get_quran_answer should not be called when cache is disabled
            mock_db.get_quran_answer.assert_not_called()

    def test_augment_question_feature(self, client, mock_settings, mock_db, mock_ansari_claude):
        """Test that augment_question adds enhancement instructions."""
        with patch("builtins.open", mock_open(read_data="Test system prompt")):
            mock_db.get_quran_answer.return_value = None
            
            response = client.post(
                "/api/v2/ayah-claude",
                json={
                    "surah": 3,
                    "ayah": 14,
                    "question": "What does this mean?",
                    "apikey": "test-api-key",
                    "augment_question": True,
                    "use_cache": False
                }
            )
            
            assert response.status_code == 200
            # Verify that AnsariClaude was called
            mock_ansari_claude.assert_called_once()
            # Verify the message passed included enhancement
            call_args = mock_ansari_claude.return_value.replace_message_history.call_args
            messages = call_args[0][0]
            assert "search relevant tafsir sources" in messages[0]["content"]

    def test_database_storage(self, client, mock_settings, mock_db, mock_ansari_claude):
        """Test that responses are stored in the database."""
        with patch("builtins.open", mock_open(read_data="Test system prompt")):
            mock_db.get_quran_answer.return_value = None
            
            response = client.post(
                "/api/v2/ayah-claude",
                json={
                    "surah": 4,
                    "ayah": 34,
                    "question": "Explain the context",
                    "apikey": "test-api-key",
                    "use_cache": True
                }
            )
            
            assert response.status_code == 200
            # Verify that store_quran_answer was called
            mock_db.store_quran_answer.assert_called_once_with(
                4, 34, "Explain the context", 
                "This is a test response about the ayah with citations."
            )

    def test_ayah_specific_system_prompt(self, client, mock_settings, mock_db, mock_ansari_claude):
        """Test that ayah-specific system prompt is loaded."""
        system_prompt_content = "Special ayah system prompt"
        
        with patch("builtins.open", mock_open(read_data=system_prompt_content)):
            mock_db.get_quran_answer.return_value = None
            
            response = client.post(
                "/api/v2/ayah-claude",
                json={
                    "surah": 5,
                    "ayah": 3,
                    "question": "What is the significance?",
                    "apikey": "test-api-key"
                }
            )
            
            assert response.status_code == 200
            # Verify AnsariClaude was initialized with the system prompt
            mock_ansari_claude.assert_called_once()
            call_args = mock_ansari_claude.call_args
            assert call_args[1]["system_prompt"] == system_prompt_content

    def test_ayah_id_calculation(self, client, mock_settings, mock_db, mock_ansari_claude):
        """Test that ayah_id is calculated correctly for tafsir filtering."""
        with patch("builtins.open", mock_open(read_data="Test system prompt")):
            mock_db.get_quran_answer.return_value = None
            
            # Test with Surah 2, Ayah 255 (Ayat al-Kursi)
            # Expected ayah_id = 2 * 1000 + 255 = 2255
            response = client.post(
                "/api/v2/ayah-claude",
                json={
                    "surah": 2,
                    "ayah": 255,
                    "question": "Explain Ayat al-Kursi",
                    "apikey": "test-api-key"
                }
            )
            
            assert response.status_code == 200
            # The ayah_id should be used in the context
            call_args = mock_ansari_claude.return_value.replace_message_history.call_args
            messages = call_args[0][0]
            assert "Surah 2, Ayah 255" in messages[0]["content"]

    def test_error_handling(self, client, mock_settings, mock_db):
        """Test that errors are handled gracefully."""
        with patch("src.ansari.app.main_api.AnsariClaude") as mock_claude:
            # Make AnsariClaude raise an exception
            mock_claude.side_effect = Exception("Test error")
            mock_db.get_quran_answer.return_value = None
            
            with patch("builtins.open", mock_open(read_data="Test system prompt")):
                response = client.post(
                    "/api/v2/ayah-claude",
                    json={
                        "surah": 1,
                        "ayah": 1,
                        "question": "Test question",
                        "apikey": "test-api-key"
                    }
                )
                
                assert response.status_code == 500
                assert response.json()["detail"] == "Internal server error"

    def test_request_validation(self, client, mock_settings):
        """Test that request validation works correctly."""
        # Missing required fields
        response = client.post(
            "/api/v2/ayah-claude",
            json={
                "surah": 1,
                # Missing ayah, question, and apikey
            }
        )
        assert response.status_code == 422  # Unprocessable Entity

        # Invalid data types
        response = client.post(
            "/api/v2/ayah-claude",
            json={
                "surah": "not-a-number",
                "ayah": 1,
                "question": "Test",
                "apikey": "test-key"
            }
        )
        assert response.status_code == 422