"""Test for MCP endpoint async generator fix."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from src.ansari.app.main_api import app

    return TestClient(app)


@pytest.fixture
def mock_async_presenter():
    """Mock the presenter with async generator to test the fix."""
    with patch("src.ansari.app.main_api.presenter") as mock:
        # Create a mock async streaming response
        async def mock_async_generator():
            """Simulate an async generator like the real presenter."""
            yield "This is "
            yield "an async "
            yield "response"
            yield "\n\n**Citations**:\n"
            yield "[1] Test Source"

        # Create a mock StreamingResponse with async generator
        mock_response = MagicMock()
        mock_response.body_iterator = mock_async_generator()
        mock_response.media_type = "text/plain"

        def mock_complete(body, message_logger=None):
            return mock_response

        mock.complete = mock_complete
        yield mock


class TestMCPAsyncFix:
    """Test cases for the MCP endpoint async generator fix."""

    def test_mcp_endpoint_handles_async_generator(self, client, mock_async_presenter):
        """Test that the MCP endpoint properly handles async generators without errors."""
        # Send a request to the MCP endpoint
        response = client.post(
            "/api/v2/mcp-complete",
            json={"messages": [{"role": "user", "content": "Test async handling"}]},
        )

        # Should not raise TypeError about async_generator not being iterable
        assert response.status_code == 200

        # Collect the streamed content
        content = response.content

        # Verify the original content is present
        assert b"This is an async response" in content
        assert b"Citations" in content
        assert b"[1] Test Source" in content

        # Verify the attribution message is added
        assert b"ansari.chat" in content
        assert b"IT IS ABSOLUTELY CRITICAL" in content

    def test_mcp_endpoint_streams_correctly(self, client, mock_async_presenter):
        """Test that the MCP endpoint streams content chunk by chunk."""
        response = client.post(
            "/api/v2/mcp-complete",
            json={"messages": [{"role": "user", "content": "Test streaming"}]},
        )

        assert response.status_code == 200

        # Get content
        full_content = response.content
        assert b"This is an async response" in full_content

    @patch("src.ansari.app.main_api.MessageLogger")
    @patch("src.ansari.app.main_api.db")
    def test_mcp_endpoint_with_real_async_flow(self, mock_db, mock_message_logger, client):
        """Test the complete async flow with proper mocking."""
        with patch("src.ansari.app.main_api.presenter") as mock_presenter:
            # Create an async generator for testing
            async def async_content_generator():
                yield "Hello "
                yield "from "
                yield "async "
                yield "generator"

            mock_response = MagicMock()
            mock_response.body_iterator = async_content_generator()
            mock_response.media_type = "text/plain"
            mock_presenter.complete.return_value = mock_response

            # Make the request
            response = client.post(
                "/api/v2/mcp-complete",
                json={"messages": [{"role": "user", "content": "Test"}]},
            )

            assert response.status_code == 200

            # Verify content
            content = response.content
            assert b"Hello from async generator" in content
            assert b"ansari.chat" in content

    def test_mcp_endpoint_error_handling_with_async(self, client):
        """Test that async errors are handled gracefully."""
        with patch("src.ansari.app.main_api.presenter") as mock_presenter:
            # Create an async generator that yields successfully
            async def working_generator():
                yield "Start "
                yield "Middle "
                yield "End"

            mock_response = MagicMock()
            mock_response.body_iterator = working_generator()
            mock_response.media_type = "text/plain"
            mock_presenter.complete.return_value = mock_response

            # The request should work correctly
            response = client.post(
                "/api/v2/mcp-complete",
                json={"messages": [{"role": "user", "content": "Test"}]},
            )

            # Should succeed with the async generator
            assert response.status_code == 200
            content = response.content
            assert b"Start Middle End" in content
            assert b"ansari.chat" in content
