"""Unit tests for the MCP (Model Context Protocol) endpoint."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from ansari.ansari_db import SourceType


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from src.ansari.app.main_api import app

    return TestClient(app)


@pytest.fixture
def mock_presenter():
    """Mock the presenter to avoid actual LLM calls."""
    with patch("src.ansari.app.main_api.presenter") as mock:
        # Create a mock streaming response
        def mock_complete(body, message_logger=None):
            def generate():
                yield "This is a test response"
                yield " with citations"
                yield "\n\n**Citations**:\n[1] Test Citation"

            from fastapi.responses import StreamingResponse

            return StreamingResponse(generate(), media_type="text/plain")

        mock.complete = mock_complete
        yield mock


class TestMCPEndpoint:
    """Test cases for the /api/v2/mcp endpoint."""

    def test_mcp_endpoint_exists(self, client):
        """Test that the MCP endpoint is registered."""
        # Send a request to the endpoint
        response = client.post("/api/v2/mcp", json={"messages": [{"role": "user", "content": "Test message"}]})
        # Should not return 404
        assert response.status_code != 404

    def test_mcp_endpoint_no_authentication_required(self, client, mock_presenter):
        """Test that the MCP endpoint does not require authentication."""
        # Send a request without any authentication headers
        response = client.post("/api/v2/mcp", json={"messages": [{"role": "user", "content": "Test message"}]})

        # Should not return 401 (Unauthorized) or 403 (Forbidden)
        assert response.status_code not in [401, 403]
        assert response.status_code == 200

    def test_mcp_endpoint_accepts_messages(self, client, mock_presenter):
        """Test that the MCP endpoint accepts a list of messages."""
        test_messages = {
            "messages": [
                {"role": "user", "content": "What is Islam?"},
                {"role": "assistant", "content": "Islam is..."},
                {"role": "user", "content": "Tell me more"},
            ]
        }

        response = client.post("/api/v2/mcp", json=test_messages)
        assert response.status_code == 200

    def test_mcp_endpoint_returns_streaming_response(self, client, mock_presenter):
        """Test that the MCP endpoint returns a streaming response."""
        response = client.post("/api/v2/mcp", json={"messages": [{"role": "user", "content": "Test"}]}, stream=True)

        assert response.status_code == 200
        # Collect the streamed content
        content = b"".join(response.iter_content())
        assert b"This is a test response" in content
        assert b"Citations" in content

    @patch("src.ansari.app.main_api.MessageLogger")
    @patch("src.ansari.app.main_api.db")
    def test_mcp_endpoint_uses_mcp_source_type(self, mock_db, mock_message_logger, client, mock_presenter):
        """Test that the MCP endpoint uses MCP as the source type."""
        # Send a request to the MCP endpoint
        response = client.post("/api/v2/mcp", json={"messages": [{"role": "user", "content": "Test"}]})

        assert response.status_code == 200

        # Verify MessageLogger was called with MCP source type
        mock_message_logger.assert_called_once()
        call_args = mock_message_logger.call_args
        assert call_args[0][1] == SourceType.MCP  # Second argument is source_type
        assert call_args[0][2] == "mcp_system_user"  # Third argument is user_id
        assert call_args[0][3].startswith("mcp_")  # Fourth argument is thread_id

    def test_mcp_endpoint_handles_empty_messages(self, client):
        """Test that the MCP endpoint handles empty message lists gracefully."""
        response = client.post("/api/v2/mcp", json={"messages": []})
        # Should handle gracefully, not crash
        assert response.status_code in [200, 400]

    def test_mcp_endpoint_handles_invalid_json(self, client):
        """Test that the MCP endpoint handles invalid JSON gracefully."""
        response = client.post("/api/v2/mcp", data="invalid json")
        # Should return a validation error
        assert response.status_code == 422  # Unprocessable Entity

    def test_mcp_endpoint_handles_missing_messages_field(self, client):
        """Test that the MCP endpoint handles missing 'messages' field."""
        response = client.post("/api/v2/mcp", json={"wrong_field": "value"})
        # Should handle the error gracefully
        # The actual behavior depends on how presenter.complete handles it
        assert response.status_code in [200, 400, 422, 500]

    @patch("src.ansari.app.main_api.logger")
    def test_mcp_endpoint_logs_requests(self, mock_logger, client, mock_presenter):
        """Test that the MCP endpoint logs incoming requests."""
        test_messages = {"messages": [{"role": "user", "content": "Test"}]}

        response = client.post("/api/v2/mcp", json=test_messages)
        assert response.status_code == 200

        # Verify logging was called
        mock_logger.info.assert_called()
        # Check that the log message contains the expected information
        log_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("v2/mcp" in str(call) for call in log_calls)


class TestMCPIntegration:
    """Integration tests for the MCP endpoint with other components."""

    @patch("src.ansari.app.main_api.AnsariClaude")
    def test_mcp_endpoint_with_ansari_claude(self, mock_ansari_claude, client):
        """Test MCP endpoint integration with AnsariClaude agent."""
        # Set up the mock to return a generator (for streaming)
        mock_instance = MagicMock()
        mock_instance.replace_message_history.return_value = (word for word in ["Test ", "response ", "with ", "citations"])
        mock_ansari_claude.return_value = mock_instance

        with patch("src.ansari.app.main_api.presenter.complete") as mock_complete:
            from fastapi.responses import StreamingResponse

            def generate():
                yield "Test response with citations"

            mock_complete.return_value = StreamingResponse(generate())

            response = client.post("/api/v2/mcp", json={"messages": [{"role": "user", "content": "Test"}]})

            assert response.status_code == 200
            content = b"".join(response.iter_content())
            assert b"Test response" in content

    def test_mcp_endpoint_thread_id_format(self, client, mock_presenter):
        """Test that thread IDs are properly formatted with MCP prefix."""
        with patch("src.ansari.app.main_api.MessageLogger") as mock_message_logger:
            response = client.post("/api/v2/mcp", json={"messages": [{"role": "user", "content": "Test"}]})

            assert response.status_code == 200

            # Get the thread_id that was passed to MessageLogger
            call_args = mock_message_logger.call_args
            thread_id = call_args[0][3]

            # Verify thread_id starts with "mcp_" and contains ISO timestamp
            assert thread_id.startswith("mcp_")
            # The rest should be an ISO timestamp
            timestamp_part = thread_id[4:]  # Remove "mcp_" prefix
            # Basic check that it looks like an ISO timestamp
            assert "T" in timestamp_part  # ISO format has T separator
            assert ":" in timestamp_part  # Has time components
