import json
import time
import asyncio
from typing import Generator

import anthropic

from ansari.agents.ansari import Ansari
from ansari.ansari_db import MessageLogger
from ansari.config import Settings
from ansari.util.prompt_mgr import PromptMgr
from ansari.ansari_logger import get_logger
from ansari.util.translation import translate_texts_parallel, parse_multilingual_data

# Set up logging
logger = get_logger(__name__)


class AnsariClaude(Ansari):
    """Claude-based implementation of the Ansari agent."""

    def __init__(self, settings: Settings, message_logger: MessageLogger = None, json_format=False):
        """Initialize the Claude-based Ansari agent.

        Args:
            settings: Application settings
            message_logger: Optional message logger instance
            json_format: Whether to use JSON format for responses
        """
        # Call parent initialization
        super().__init__(settings, message_logger, json_format)

        # Initialize Claude-specific client
        self.client = anthropic.Anthropic()

        # Convert tool descriptions to Claude format
        self.tools = [self._convert_tool_format(x) for x in self.tools]

        # Initialize empty message history for Claude (no system message)
        self.message_history = []

        # Initialize citation tracking
        self.citations = []

    def validate_message(self, message):
        """Validates message structure for consistency before logging.

        This method ensures that messages have the expected structure based on their role
        and type, which helps maintain consistency between in-memory and database
        representations.

        Args:
            message: The message to validate

        Returns:
            bool: True if the message is valid, False otherwise
        """
        if not isinstance(message, dict):
            logger.warning("Message must be a dictionary")
            return False

        if "role" not in message:
            logger.warning("Message must have a role")
            return False

        if "content" not in message:
            logger.warning("Message must have content")
            return False

        role = message["role"]
        content = message["content"]

        # Assistant messages should have list content with typed blocks
        if role == "assistant":
            if not isinstance(content, list):
                logger.warning("Assistant message content should be a list")
                return False

            # Check if any block is missing a type
            for block in content:
                if not isinstance(block, dict) or "type" not in block:
                    logger.warning("Assistant message content blocks must have a type")
                    return False

                # Text blocks must have text
                if block["type"] == "text" and "text" not in block:
                    logger.warning("Text blocks must have text")
                    return False

                # Tool use blocks must have id, name, and input
                if block["type"] == "tool_use":
                    if "id" not in block:
                        logger.warning("Tool use blocks must have an id")
                        return False
                    if "name" not in block:
                        logger.warning("Tool use blocks must have a name")
                        return False
                    if "input" not in block:
                        logger.warning("Tool use blocks must have input")
                        return False

        # User messages with tool results should have the right structure
        if role == "user" and isinstance(content, list):
            tool_result_blocks = [b for b in content if b.get("type") == "tool_result"]
            if tool_result_blocks:
                for block in tool_result_blocks:
                    if "tool_use_id" not in block:
                        logger.warning("Tool result blocks must have a tool_use_id")
                        return False
                    if "content" not in block:
                        logger.warning("Tool result blocks must have content")
                        return False

        return True

    def _log_message(self, message):
        """Log a message using the message_logger with complete representation from message_history.

        This ensures that the messages logged to the database match what's in the message_history.
        The database will store this in a flattened format which will be reconstructed during retrieval.
        """
        if not self.message_logger:
            return

        # Validate message structure
        if not self.validate_message(message):
            logger.warning(f"Invalid message structure: {message}")
            return

        logger.info(f"Logging {message}")
        content = message["content"]
        tool_details = []
        ref_list = []
        tool_name = message.get("tool_name", None)

        # Handle different message content formats
        if isinstance(content, list):
            ref_list = [block for block in content if block.get("type") == "document"]

            # Extract tool details from content for assistant messages
            if message["role"] == "assistant":
                tool_use_blocks = [block for block in content if block.get("type") == "tool_use"]
                # If we have tool use blocks, properly extract and format their details
                if tool_use_blocks:
                    tool_name = tool_use_blocks[0].get("name")
                    tool_details = {
                        "id": tool_use_blocks[0].get("id"),
                        "type": "function",
                        "function": {
                            "name": tool_use_blocks[0].get("name"),
                            "arguments": json.dumps(tool_use_blocks[0].get("input", {})),
                        },
                    }
            # Extract tool result details for user messages
            elif message["role"] == "user":
                tool_result_blocks = [block for block in content if block.get("type") == "tool_result"]
                if tool_result_blocks:
                    tool_details = tool_result_blocks

        # Log the message with appropriate structure
        self.message_logger.log(
            role=message["role"],
            content=content,
            tool_name=tool_name,
            tool_details=tool_details,
            ref_list=ref_list,
        )

    def replace_message_history(self, message_history: list[dict], use_tool=True, stream=True):
        """
        Replaces the current message history (stored in Ansari) with the given message history,
        and then processes it to generate a response from Ansari.
        """
        # AnsariClaude doesn't use system message, so we don't need to prefix it
        self.message_history = message_history

        for m in self.process_message_history(use_tool, stream):
            if m:
                yield m

    def _convert_tool_format(self, tool):
        """Convert from OpenAI's function calling format to Claude's format.

        OpenAI format:
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "...",
                "parameters": {
                    "type": "object",
                    "properties": {...},
                    "required": [...]
                }
            }
        }

        Claude format:
        {
            "name": "get_weather",
            "description": "...",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
        """
        return {
            "name": tool["function"]["name"],
            "description": tool["function"]["description"],
            "input_schema": tool["function"]["parameters"],
        }

    def process_tool_call(self, tool_name: str, tool_args: dict, tool_id: str):
        """Process a tool call and return its result as a list."""
        if tool_name not in self.tool_name_to_instance:
            logger.warning(f"Unknown tool name: {tool_name}")
            return ([], [])

        try:
            query = tool_args["query"]  # tool_args is now a dict, not a string

        except KeyError as e:  # Remove JSONDecodeError since we're not parsing JSON
            logger.error(f"Failed to parse tool arguments: {e}")
            logger.error(f"Raw arguments: {tool_args}")
            raise

        tool_instance = self.tool_name_to_instance[tool_name]

        # Get raw results
        results = tool_instance.run(query)

        # Format results in different ways
        tool_result = tool_instance.format_as_tool_result(results)
        reference_list = tool_instance.format_as_ref_list(results)

        if not reference_list:
            return (tool_result, [])

        logger.info(f"Got {len(reference_list)} results from {tool_name}")

        # Return results
        return (tool_result, reference_list)

    def process_one_round(self) -> Generator[str, None, None]:
        """Process one round of conversation.

        Yields:
            Chunks of the response text

        Side effect:
            - Updates the message history with at most one user message and one assistant message
            - Logs these messages once they're complete
        """
        prompt_mgr = PromptMgr()
        system_prompt = prompt_mgr.bind("system_msg_claude").render()

        logger.info(f"Sending messages to Claude: {json.dumps(self.message_history, indent=2)}")

        # Create API request parameters
        params = {
            "model": self.settings.ANTHROPIC_MODEL,
            "system": system_prompt,
            "messages": self.message_history,
            "max_tokens": 4096,
            "temperature": 0.0,
            "stream": True,  # Always stream
        }
        params["tools"] = self.tools

        failures = 0
        response = None

        # Retry loop for API calls
        while not response:
            try:
                response = self.client.messages.create(**params)
            except Exception as e:
                failures += 1
                logger.warning(f"API call failed: {str(e)}")

                if failures >= self.settings.MAX_FAILURES:
                    logger.error("Max retries exceeded")
                    raise

                logger.info("Retrying in 5 seconds...")
                time.sleep(5)
                continue

        # Variables to accumulate complete messages before adding to history
        assistant_text = ""
        tool_calls = []

        # Variables for processing the streaming response
        current_tool = None
        current_json = ""

        logger.info("Processing response chunks")

        """ Warning: This is probably the most complex code in all of Ansari. 

        This is a finite state machine that processes the response chunks.

        A summary of what the code does is: 
    
        - If it's a content block start and it's a tool call, capture the key parameters of the tool call. 
        - If it's a content block delta that is text, add the text to the assistant's message. 
        - If it's a content block delta that is a citation, add the citation to the citations list and 
         yield a string that represents the citation.
         - If it's tool parameters, accumulate the tool paramters into the current tool.  

        """
        for chunk in response:
            logger.debug(f"Raw chunk: {chunk}")

            if chunk.type == "content_block_start":
                if chunk.content_block.type == "tool_use":
                    # Start of a tool call
                    logger.info(f"Starting tool call with id: {chunk.content_block.id}, name: {chunk.content_block.name}")
                    current_tool = {
                        "type": "tool_use",
                        "id": chunk.content_block.id,
                        "name": chunk.content_block.name,
                    }
                    logger.debug(f"Starting tool call: {current_tool}")

            elif chunk.type == "content_block_delta":
                if hasattr(chunk.delta, "text"):
                    text = chunk.delta.text
                    assistant_text += text
                    yield text
                elif getattr(chunk.delta, "type", None) == "citations_delta":
                    # Process citation delta
                    citation = chunk.delta.citation
                    self.citations.append(citation)
                    citation_ref = f" [{len(self.citations)}] "
                    assistant_text += citation_ref
                    yield citation_ref
                elif hasattr(chunk.delta, "partial_json"):
                    # Accumulate JSON for tool arguments
                    current_json += chunk.delta.partial_json

            elif chunk.type == "content_block_stop":
                if current_tool:
                    try:
                        arguments = json.loads(current_json)
                        logger.debug(f"Tool arguments: {arguments}")
                        current_tool["input"] = arguments
                        tool_calls.append(current_tool)

                        # Reset for next tool
                        current_tool = None
                        current_json = ""

                    except Exception as e:
                        error_msg = f"Tool call failed: {str(e)}"
                        logger.error(error_msg)
                        raise

            elif chunk.type == "message_delta":
                if chunk.delta.stop_reason == "tool_use":
                    logger.debug("Message stopped for tool use")
                elif hasattr(chunk.delta, "text"):
                    text = chunk.delta.text
                    assistant_text += text
                    yield text

            elif chunk.type == "message_stop":
                # Add citations list at the end if there were any citations
                if self.citations:
                    citations_text = "\n\n**Citations**:\n"
                    logger.debug(f"Full Citations: {self.citations}")

                    # Process each citation
                    for i, citation in enumerate(self.citations, 1):
                        cited_text = getattr(citation, "cited_text", "")
                        title = getattr(citation, "document_title", "")
                        citations_text += f"[{i}] {title}:\n"

                        # Since we're now storing only Arabic text in the document data,
                        # we can directly use the cited text as Arabic and translate it
                        arabic_text = cited_text
                        
                        try:
                            # Translate the Arabic text to English
                            english_translation = asyncio.run(translate_texts_parallel([arabic_text], "en", "ar"))[0]
                            
                            # Add both Arabic and English to the citations with extra newlines
                            citations_text += f" Arabic: {arabic_text}\n\n"
                            citations_text += f" English: {english_translation}\n"
                        except Exception as e:
                            # If translation fails, log the error and just show the Arabic text
                            logger.error(f"Translation failed: {e}")
                            citations_text += f" Arabic: {arabic_text}\n\n"
                            citations_text += f" English: [Translation unavailable]\n"

                    assistant_text += citations_text
                    yield citations_text

                # We are done with the message.
                # At this point the next thing we should log is

                # Add the assistant's message to history
                # This is both the text and the tool use calls.
                content_blocks = []

                # Only include text block if there's non-empty text
                if assistant_text.strip():
                    content_blocks.append({"type": "text", "text": assistant_text.strip()})

                # Always include tool_calls in content blocks if present
                # This ensures the tool use call is saved in the message history
                if tool_calls:
                    content_blocks.extend(tool_calls)

                # Create the message content based on whether we have content blocks
                message_content = None
                if content_blocks:
                    message_content = content_blocks
                else:
                    # If no content blocks, use a single empty text element
                    message_content = [{"type": "text", "text": ""}]

                # Create the assistant message for the message history
                # Don't include tool_name in the message sent to Claude API
                assistant_message = {"role": "assistant", "content": message_content}

                # Add to message history
                self.message_history.append(assistant_message)

                # For logging, create a copy with tool_name for database storage
                if tool_calls:
                    log_message = assistant_message.copy()
                    log_message["tool_name"] = tool_calls[0]["name"]
                    # Log the message with tool_name for database
                    self._log_message(log_message)
                else:
                    # Log the regular message
                    self._log_message(self.message_history[-1])

                # Process any accumulated tool calls
                # Note: We only create a user message if there were tool calls?
                if tool_calls:
                    logger.debug(f"Processing {len(tool_calls)} accumulated tool calls")
                    for tc in tool_calls:
                        try:
                            # Process the tool call
                            (tool_result, reference_list) = self.process_tool_call(tc["name"], tc["input"], tc["id"])

                            logger.info(f"Reference list: {json.dumps(reference_list, indent=2)}")

                            # Check what type of data we're dealing with
                            document_blocks = []
                            logger.debug(f"Reference list type: {type(reference_list)}")
                            if reference_list and len(reference_list) > 0:
                                logger.debug(f"First reference item type: {type(reference_list[0])}")

                            # All references are now dictionaries, so we can directly use them
                            document_blocks = reference_list

                            # Store the tool call details in the assistant message for proper reconstruction
                            # This ensures the database has the tool_use data needed for replay
                            # We'll use these values directly when needed

                            # Add tool result and document blocks in the same message
                            self.message_history.append(
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": tc["id"],
                                            "content": "Please see the references below.",
                                        }
                                    ]
                                    + document_blocks,
                                }
                            )
                            # Log the tool result message with tool details to ensure proper saving
                            self._log_message(self.message_history[-1])

                        except Exception as e:
                            logger.error(f"Error processing tool call: {str(e)}")
                            # Add error as tool result
                            self.message_history.append(
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": tc["id"],
                                            "content": [{"type": "text", "text": str(e)}],
                                        }
                                    ],
                                }
                            )
                            # Log the error message
                            self._log_message(self.message_history[-1])

    def process_message_history(self, use_tool=True, stream=True):
        """
        This is the main loop that processes the message history.
        It yields from the process_one_round method until the last message is an assistant message.
        The assumption coming in to this is that it ends with a user message.
        """

        count = 0

        # Track tool_use_ids to ensure tool_result blocks have matching tool_use blocks
        tool_use_ids = set()

        # First pass: collect all tool_use IDs
        for msg in self.message_history:
            if msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and "id" in block:
                        tool_use_ids.add(block["id"])
                        logger.debug(f"Found tool_use block with ID: {block['id']}")

        logger.debug(f"Found tool_use_ids: {tool_use_ids}")

        # Second pass: ensure all messages have proper format for the API
        for i in range(len(self.message_history)):
            msg = self.message_history[i]

            # All assistant messages must use the block format
            if msg.get("role") == "assistant":
                if isinstance(msg.get("content"), str):
                    # Convert string to text block
                    self.message_history[i]["content"] = [{"type": "text", "text": msg["content"]}]
                elif isinstance(msg.get("content"), list):
                    # Check if content is already in correct format with blocks having "type" field
                    has_valid_blocks = all(isinstance(item, dict) and "type" in item for item in msg["content"])
                    if not has_valid_blocks:
                        # If not blocks, convert the whole list to a text block
                        logger.warning(f"Fixing assistant message with improper content format: {msg['content']}")
                        self.message_history[i]["content"] = [{"type": "text", "text": str(msg["content"])}]
                else:
                    # Convert any other content type to text block
                    self.message_history[i]["content"] = [{"type": "text", "text": str(msg["content"])}]

            # User messages with tool_result need to have matching tool_use blocks
            elif msg.get("role") == "user" and isinstance(msg.get("content"), list):
                fixed_content = []
                has_invalid_tool_result = False

                for block in msg["content"]:
                    # Check if this is a tool_result block
                    is_tool_result = isinstance(block, dict) and (block.get("type") == "tool_result" or "tool_use_id" in block)

                    if is_tool_result:
                        # Ensure it has type field
                        if "type" not in block:
                            block["type"] = "tool_result"
                            logger.warning("Added missing 'type': 'tool_result' to block")

                        # Check if the tool_use_id exists in our collected IDs
                        if "tool_use_id" in block and block["tool_use_id"] not in tool_use_ids:
                            has_invalid_tool_result = True
                            logger.warning(f"Found tool_result with ID {block['tool_use_id']} but no matching tool_use block")
                            # Skip this block - it has no matching tool_use
                            continue

                    # Keep this block
                    fixed_content.append(block)

                # If we had to remove invalid tool_result blocks and now have an empty list,
                # replace with a simple text message
                if has_invalid_tool_result:
                    if not fixed_content:
                        self.message_history[i]["content"] = "Tool result (missing matching tool_use)"
                    else:
                        self.message_history[i]["content"] = fixed_content

        # Check if the last message is a user message and needs to be logged.
        # This check avoids double-logging the user message which is already logged in the parent Ansari.process_input method
        if len(self.message_history) > 0 and self.message_history[-1]["role"] == "user":
            # Check if this message was logged by parent class by inspecting if it exists in the logger
            should_log = True
            if self.message_logger and hasattr(self.message_logger, "messages"):
                # If the last logged message in the logger matches the last message in history, don't log it again
                if (
                    len(self.message_logger.messages) > 0
                    and self.message_logger.messages[-1]["role"] == "user"
                    and self.message_logger.messages[-1]["content"] == self.message_history[-1]["content"]
                ):
                    should_log = False

            if should_log:
                # Log the message if needed
                self._log_message(self.message_history[-1])

        while self.message_history[-1]["role"] != "assistant":
            logger.info(f"Processing message iteration: {count}")
            logger.debug("Current message history:\n" + "-" * 60)
            for i, msg in enumerate(self.message_history):
                logger.debug(f"Message {i}:\n{json.dumps(msg, indent=2)}")
            logger.debug("-" * 60)
            # This is pretty complicated so leaving a comment.
            # We want to yield from so that we can send the sequence through the input
            # Also use tools only if we haven't tried too many times (failure)
            #  and if the last message was not from the tool (success!)
            yield from self.process_one_round()
            count += 1
