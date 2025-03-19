import pytest
import copy
from src.ansari.agents.ansari_claude import AnsariClaude
from src.ansari.config import get_settings


class TestAnsariClaudeDocumentLimiting:
    """Test the document limiting functionality in AnsariClaude class."""

    def setup_method(self):
        """Set up test environment with AnsariClaude instance."""
        settings = get_settings()
        self.ansari_claude = AnsariClaude(settings)

        # Create a helper method to create a message with documents
        def create_message_with_docs(role, num_docs, message_index=0):
            """Create a message with specified number of document blocks."""
            content = []
            for i in range(num_docs):
                content.append(
                    {
                        "type": "document",
                        "title": f"Document {message_index}-{i}",
                        "source": {"type": "text", "media_type": "text/plain", "data": f"Content {message_index}-{i}"},
                        "context": f"Context for document {message_index}-{i}",
                        "citations": {"enabled": True},
                    }
                )

            # Add a tool_result block for messages that include docs
            if role == "user" and num_docs > 0:
                content.insert(
                    0,
                    {
                        "type": "tool_result",
                        "tool_use_id": f"tool-{message_index}",
                        "content": "Please see the references below.",
                    },
                )

            return {"role": role, "content": content}

        self.create_message_with_docs = create_message_with_docs

    def test_no_documents_no_change(self):
        """Test that message history with no documents is unchanged."""
        # Set up message history with no documents
        original_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": [{"type": "text", "text": "Hi there!"}]},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": [{"type": "text", "text": "I'm doing well!"}]},
        ]

        # Make a copy for later comparison
        self.ansari_claude.message_history = copy.deepcopy(original_history)
        limited_history = self.ansari_claude.limit_documents_in_message_history(max_documents=100)

        # Verify history is unchanged (deep compare)
        assert limited_history == original_history

    def test_under_limit_no_change(self):
        """Test that message history with documents under the limit is unchanged."""
        # Set up message history with 50 documents (below the limit of 100)
        original_history = [
            # First user/assistant exchange with 10 documents
            self.create_message_with_docs("user", 10, 0),
            {"role": "assistant", "content": [{"type": "text", "text": "Here's the information"}]},
            # Second exchange with 15 documents
            self.create_message_with_docs("user", 15, 1),
            {"role": "assistant", "content": [{"type": "text", "text": "More information"}]},
            # Third exchange with 25 documents
            self.create_message_with_docs("user", 25, 2),
            {"role": "assistant", "content": [{"type": "text", "text": "Final information"}]},
        ]

        # Make a copy for later comparison
        self.ansari_claude.message_history = copy.deepcopy(original_history)
        limited_history = self.ansari_claude.limit_documents_in_message_history(max_documents=100)

        # Verify history is unchanged since we're under the limit
        assert limited_history == original_history

        # Count documents to verify
        doc_count = self._count_documents(limited_history)
        assert doc_count == 50

    def test_over_limit_oldest_removed(self):
        """Test that oldest documents are removed when over the limit."""
        # Set up message history with 150 documents (over the limit of 100)
        original_history = [
            # First exchange with 60 documents (these should be partially removed)
            self.create_message_with_docs("user", 60, 0),
            {"role": "assistant", "content": [{"type": "text", "text": "First response"}]},
            # Second exchange with 40 documents (these should be kept)
            self.create_message_with_docs("user", 40, 1),
            {"role": "assistant", "content": [{"type": "text", "text": "Second response"}]},
            # Third exchange with 50 documents (these should be kept)
            self.create_message_with_docs("user", 50, 2),
            {"role": "assistant", "content": [{"type": "text", "text": "Third response"}]},
        ]

        # Make a copy for later comparison
        self.ansari_claude.message_history = copy.deepcopy(original_history)
        limited_history = self.ansari_claude.limit_documents_in_message_history(max_documents=100)

        # Count documents in limited history
        doc_count = self._count_documents(limited_history)
        assert doc_count == 100, f"Expected 100 documents, got {doc_count}"

        # Verify that oldest documents were removed
        # The first message originally had 60 docs, should now have only 10
        first_msg_docs = self._count_documents_in_message(limited_history[0])
        assert first_msg_docs == 10, f"Expected 10 documents in first message, got {first_msg_docs}"

        # Second message should still have all 40 docs
        second_msg_docs = self._count_documents_in_message(limited_history[2])
        assert second_msg_docs == 40, f"Expected 40 documents in second message, got {second_msg_docs}"

        # Third message should still have all 50 docs
        third_msg_docs = self._count_documents_in_message(limited_history[4])
        assert third_msg_docs == 50, f"Expected 50 documents in third message, got {third_msg_docs}"

        # Check specific documents to ensure oldest were removed
        # First message should keep documents 50-59 (the most recent 10)
        doc_titles = self._get_document_titles(limited_history[0])
        expected_titles = [f"Document 0-{i}" for i in range(50, 60)]
        assert sorted(doc_titles) == sorted(expected_titles), f"Expected titles {expected_titles}, got {doc_titles}"

    def test_custom_limit(self):
        """Test that custom max_documents limit works."""
        # Set up message history with 50 documents
        original_history = [
            self.create_message_with_docs("user", 20, 0),
            {"role": "assistant", "content": [{"type": "text", "text": "First response"}]},
            self.create_message_with_docs("user", 30, 1),
            {"role": "assistant", "content": [{"type": "text", "text": "Second response"}]},
        ]

        # Make a copy for later comparison
        self.ansari_claude.message_history = copy.deepcopy(original_history)

        # Use a custom limit of 25 (lower than the 50 documents we have)
        limited_history = self.ansari_claude.limit_documents_in_message_history(max_documents=25)

        # Count documents in limited history
        doc_count = self._count_documents(limited_history)
        assert doc_count == 25, f"Expected 25 documents, got {doc_count}"

        # First message should have 0 documents left (all 20 were removed)
        first_msg_docs = self._count_documents_in_message(limited_history[0])
        assert first_msg_docs == 0, f"Expected 0 documents in first message, got {first_msg_docs}"

        # Second message should have 25 documents left (5 were removed)
        second_msg_docs = self._count_documents_in_message(limited_history[2])
        assert second_msg_docs == 25, f"Expected 25 documents in second message, got {second_msg_docs}"

        # Check that the 25 documents kept are the most recent ones
        doc_titles = self._get_document_titles(limited_history[2])
        expected_titles = [f"Document 1-{i}" for i in range(5, 30)]  # Documents 5-29 from message 1
        assert sorted(doc_titles) == sorted(expected_titles), f"Expected titles {expected_titles}, got {doc_titles}"

    def _count_documents(self, message_history):
        """Helper method to count document blocks in a message history."""
        count = 0
        for msg in message_history:
            if isinstance(msg.get("content"), list):
                count += sum(1 for block in msg["content"] if isinstance(block, dict) and block.get("type") == "document")
        return count

    def _count_documents_in_message(self, message):
        """Helper method to count document blocks in a single message."""
        if not isinstance(message.get("content"), list):
            return 0
        return sum(1 for block in message["content"] if isinstance(block, dict) and block.get("type") == "document")

    def _get_document_titles(self, message):
        """Helper method to get titles of document blocks in a message."""
        if not isinstance(message.get("content"), list):
            return []
        return [
            block.get("title") for block in message["content"] if isinstance(block, dict) and block.get("type") == "document"
        ]


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
