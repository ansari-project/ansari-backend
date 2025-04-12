import asyncio
import copy
import json
import time
from typing import Generator

import sentry_sdk

from ansari.agents.ansari import Ansari
from ansari.ansari_db import MessageLogger
from ansari.ansari_logger import get_logger
from ansari.config import Settings, get_settings
from ansari.util.prompt_mgr import PromptMgr
from ansari.util.translation import parse_multilingual_data, translate_texts_parallel
from ansari.util.general_helpers import get_language_from_text, trim_citation_title

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

        # Log environment information for debugging
        try:
            import anthropic
            import sys
            import platform

            logger.info(f"Python version: {sys.version}")
            logger.info(f"Platform: {platform.platform()}")
            logger.info(f"Anthropic client version: {anthropic.__version__}")

            # Log API key configuration (safely)
            api_key_status = "Set" if hasattr(settings, "ANTHROPIC_API_KEY") and settings.ANTHROPIC_API_KEY else "Not set"
            logger.info(f"ANTHROPIC_API_KEY status: {api_key_status}")

            # Log model configuration
            logger.info(f"Using model: {settings.ANTHROPIC_MODEL}")
        except Exception as e:
            logger.error(f"Error logging environment info: {str(e)}")

        # Initialize Claude-specific client
        try:
            self.client = anthropic.Anthropic()
            logger.debug("Successfully initialized Anthropic client")
        except Exception as e:
            logger.error(f"Error initializing Anthropic client: {str(e)}")
            raise

        # Convert tool descriptions to Claude format
        self.tools = [self._convert_tool_format(x) for x in self.tools]
        logger.debug(f"Converted {len(self.tools)} tools to Claude format")

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
        logger.debug(f"Validating message with role: {message.get('role', 'unknown')}")

        if not isinstance(message, dict):
            logger.warning(f"Message must be a dictionary, got {type(message)}")
            return False

        if "role" not in message:
            logger.warning("Message must have a role")
            return False

        if "content" not in message:
            logger.warning(f"Message with role '{message['role']}' must have content")
            return False

        role = message["role"]
        content = message["content"]
        logger.debug(f"Validating {role} message with content type: {type(content)}")

        # Assistant messages should have list content with typed blocks
        if role == "assistant":
            if not isinstance(content, list):
                logger.warning(f"Assistant message content should be a list, got {type(content)}")
                logger.debug(f"Invalid assistant content: {content}")
                return False

            # Check if any block is missing a type
            for i, block in enumerate(content):
                logger.debug(f"Validating assistant content block {i} of type: {type(block)}")

                if not isinstance(block, dict):
                    logger.warning(f"Assistant message content block {i} must be a dict, got {type(block)}")
                    return False

                if "type" not in block:
                    logger.warning(f"Assistant message content block {i} must have a type")
                    logger.debug(f"Invalid block without type: {block}")
                    return False

                # Text blocks must have text
                if block["type"] == "text" and "text" not in block:
                    logger.warning(f"Text block {i} must have text")
                    logger.debug(f"Invalid text block: {block}")
                    return False

                # Tool use blocks must have id, name, and input
                if block["type"] == "tool_use":
                    if "id" not in block:
                        logger.warning(f"Tool use block {i} must have an id")
                        logger.debug(f"Invalid tool use block: {block}")
                        return False
                    if "name" not in block:
                        logger.warning(f"Tool use block {i} must have a name")
                        logger.debug(f"Invalid tool use block: {block}")
                        return False
                    if "input" not in block:
                        logger.warning(f"Tool use block {i} must have input")
                        logger.debug(f"Invalid tool use block: {block}")
                        return False

        # User messages with tool results should have the right structure
        if role == "user" and isinstance(content, list):
            tool_result_blocks = [b for b in content if b.get("type") == "tool_result"]
            logger.debug(f"Found {len(tool_result_blocks)} tool result blocks in user message")

            if tool_result_blocks:
                for i, block in enumerate(tool_result_blocks):
                    if "tool_use_id" not in block:
                        logger.warning(f"Tool result block {i} must have a tool_use_id")
                        logger.debug(f"Invalid tool result block: {block}")
                        return False
                    if "content" not in block:
                        logger.warning(f"Tool result block {i} must have content")
                        logger.debug(f"Invalid tool result block: {block}")
                        return False

        logger.debug(f"Message validation successful for {role} message")
        return True

    def _log_message(self, message):
        """Log a message using the message_logger with complete representation from message_history.

        This ensures that the messages logged to the database match what's in the message_history.
        The database will store this in a flattened format which will be reconstructed during retrieval.
        """
        role = message.get("role", "Unknown")
        tool_name = message.get("tool_name")
        tool_name_log = " (tool_name=" + tool_name + ")" if tool_name else ""
        content = message.get("content")

        logger.debug(
            f"_log_message called with message role: {role}{tool_name_log}, "
            f"content type: {type(content)}, "
            f"message_history length: {len(self.message_history)}"
        )

        if not self.message_logger:
            logger.warning("No message_logger available, skipping message logging")
            return

        # Validate message structure
        if not self.validate_message(message):
            logger.warning(f"Invalid message structure: {message}")
            return

        logger.info(f"Logging {message}")
        try:
            self.message_logger.log(message)
            logger.debug(f"Successfully logged message with role: {message['role']}")
        except Exception as e:
            logger.error(f"Error logging message: {str(e)}")
            logger.error(f"Message that failed to log: {message}")

    def replace_message_history(self, message_history: list[dict], use_tool=True):
        """
        Replaces the current message history (stored in Ansari) with the given message history,
        and then processes it to generate a response from Ansari.
        """
        # AnsariClaude doesn't use system message, so we don't need to prefix it
        # Remove message IDs from the history before sending to Claude
        cleaned_history = []
        for msg in message_history:
            msg_copy = msg.copy()
            if "id" in msg_copy:
                del msg_copy["id"]
            cleaned_history.append(msg_copy)

        self.message_history = cleaned_history

        # Yield Ansari's response to the user
        for m in self.process_message_history(use_tool):
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
            logger.warning(f"No references found for tool call: {tool_name}")
            return (tool_result, [])

        logger.info(f"Got {len(reference_list)} results from {tool_name}")

        # Return results
        return (tool_result, reference_list)

    def _separate_tool_result_from_preceding_text(self):
        """
        Corner case: if we our current history is like this:

        ```json
        [

            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "QUESTION THAT WILL MAKE LLM USE A TOOL"
                    }
                ]
            },
        ]
        ```

        Then, when we enter process_one_round(), the following will happen (logs):
        * Processing chunk #1 of type: message_start
        * Processing chunk #2 of type: content_block_start
        * Content block #1 start: text
        * Content block start but not a tool use: ...
        * Processing chunk #3 of type: content_block_delta
        * Adding text delta: 'START OF LLM RESPONSE' (truncated)
        * Processing chunk #...
        * Adding text delta: ...
        * ...
        * Adding text delta: 'TOOL RESULT:'
        * Processing chunk #8 of type: content_block_stop
        * Content block stop received
        * Processing chunk #9 of type: content_block_start
        * Content block #2 start: tool_use
        * ...

        so then, after the output of tool call is added to self.message_history, it will be like this:
        ```json
        [

            {
                ...
                        "text": "QUESTION THAT WILL MAKE LLM USE A TOOL"
                ...
            },

            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01CQJoWaPFZYNjrzjdLsxEeZ",
                        "name": "search_mawsuah",
                        "input": {
                            "query": "\u062d\u0643\u0645 ..."
                        }
                    }
                ]
            },

            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01CQJoWaPFZYNjrzjdLsxEeZ",
                        "content": "Please see the references below."
                    },
                    {
                        "type": "document",
                        ...
                    }
                ]
            }
        ]
        ```

        Then, when we enter process_one_round(), the following will happen (logs):
        * Processing chunk #1 of type: message_start
        * Processing chunk #2 of type: content_block_start
        * Content block #1 start: text
        * Content block start but not a tool use: ...
        * Processing chunk #3 of type: content_block_delta
        * Adding text delta: 'START OF LLM RESPONSE (PARAPHRASED FROM TOOL RESULT)' (truncated)

        So, "TOOL RESULT:" (at the top) will be directly concatenated to "START OF ...".
        But we want to leave `\n\n` between them, so that's what this function does.

        Therefore, this function should prefix the start of an assistant response IFF:
        * The last message in the history is a "tool_result"
        * Content block's type is "start" (that's where this function will be called)
        """

        if (
            (msg := self.message_history[-1])
            and (content := msg.get("content"))
            and len(content) > 0
            and (content[0].get("type", "") == "tool_result")
        ):
            return "\n\n"
        else:
            return ""

    def process_one_round(self) -> Generator[str, None, None]:
        """Process one round of conversation.

        Yields:
            Chunks of the response text

        Side effect:
            - Updates the message history with at most one user message and one assistant message
            - Logs these messages once they're complete
        """
        # ======================================================================
        # 1. API REQUEST PREPARATION AND EXECUTION
        # ======================================================================
        prompt_mgr = PromptMgr()
        system_prompt = prompt_mgr.bind("system_msg_claude").render()

        # Log the `self.message_history`
        if get_settings().DEV_MODE:
            # In DEV_MODE, log the full message history to a file for inspection
            json_file_path = "./logs/last_msg_hist.json"
            with open(json_file_path, "w") as f:
                json.dump(self.message_history, f, indent=4)
            logger.debug(f"Dumped full message history to {json_file_path}")
        else:
            # In production, log the message history in the terminal
            logger.info(f"Sending messages to Claude: {json.dumps(self.message_history, indent=2)}")

        # Limit documents in message history to prevent Claude from crashing
        # This creates a copy of the message history, preserving the original
        limited_history = self.limit_documents_in_message_history(max_documents=100)

        # Create API request parameters with the limited history
        params = {
            "model": self.settings.ANTHROPIC_MODEL,
            "system": system_prompt,
            "messages": limited_history,  # Use the limited version for API call
            "max_tokens": 4096,
            "temperature": 0.0,
            "stream": True,  # Always stream
        }
        params["tools"] = self.tools

        # Count documents in original vs limited history for logging
        orig_doc_count = sum(
            sum(1 for block in msg.get("content", []) if isinstance(block, dict) and block.get("type") == "document")
            for msg in self.message_history
            if isinstance(msg.get("content"), list)
        )
        limited_doc_count = sum(
            sum(1 for block in msg.get("content", []) if isinstance(block, dict) and block.get("type") == "document")
            for msg in limited_history
            if isinstance(msg.get("content"), list)
        )

        # Log API request parameters (excluding the full message history for brevity)
        logger_params = params.copy()
        doc_info = f"[{len(self.message_history)} messages with {limited_doc_count} documents"
        if orig_doc_count != limited_doc_count:
            doc_info += f", limited from {orig_doc_count} documents]"
        else:
            doc_info += "]"
        logger_params["messages"] = doc_info
        logger_params["system"] = system_prompt[:100] + "..." if len(system_prompt) > 100 else system_prompt
        logger.info(f"API request parameters: {logger_params}")

        failures = 0
        response = None
        start_time = time.time()

        # Retry loop for API calls
        while not response:
            try:
                logger.debug("Calling Anthropic API...")
                response = self.client.messages.create(**params)
                elapsed = time.time() - start_time
                logger.info(f"API connection established after {elapsed:.2f}s")
            except Exception as e:
                failures += 1
                elapsed = time.time() - start_time
                logger.warning(f"API call failed after {elapsed:.2f}s: {str(e)}")
                logger.error(f"Error type: {type(e).__name__}")

                if hasattr(e, "__dict__"):
                    logger.error(f"Error details: {e.__dict__}")

                # If in DEV_MODE and it's the first failure, dump message history to file
                if get_settings().DEV_MODE and failures == 1:
                    json_file_path = "./logs/last_err_msg_hist.json"
                    with open(json_file_path, "w") as f:
                        json.dump(self.message_history, f, indent=4)
                    logger.info(f"Dumped message history to {json_file_path}")

                if failures >= self.settings.MAX_FAILURES:
                    logger.error("Max retries exceeded")
                    raise

                logger.info("Retrying in 5 seconds...")
                time.sleep(5)
                continue

        # ======================================================================
        # 2. INITIALIZE STATE VARIABLES
        # ======================================================================
        # Variables to accumulate complete messages before adding to history
        assistant_text = ""  # Accumulated assistant response text
        tool_calls = []  # List of complete tool calls
        response_finished = False  # Flag to prevent duplicate processing

        # Variables for processing the streaming response
        current_tool = None  # Current tool being processed
        current_json = ""  # Accumulated JSON for current tool

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
        logger.debug("Starting to process response stream")
        chunk_count = 0
        content_block_count = 0
        message_delta_count = 0

        # ======================================================================
        # 3. PROCESS STREAMING RESPONSE (STATE MACHINE)
        # ======================================================================
        # This is a finite state machine that processes different types of chunks:
        # - content_block_start: Start of a content block (text or tool_use)
        # - content_block_delta: Updates to content (text, citations, tool JSON)
        # - content_block_stop: End of a content block
        # - message_delta: Top-level message updates, including termination
        # - message_stop: Final message termination
        for chunk in response:
            chunk_count += 1
            logger.debug(f"Processing chunk #{chunk_count} of type: {chunk.type}")

            if chunk.type == "content_block_start":
                content_block_count += 1
                logger.debug(f"Content block #{content_block_count} start: {getattr(chunk.content_block, 'type', 'unknown')}")

                if (
                    hasattr(chunk, "content_block")
                    and hasattr(chunk.content_block, "type")
                    and chunk.content_block.type == "tool_use"
                ):
                    # Start of a tool call
                    logger.info(f"Starting tool call with id: {chunk.content_block.id}, name: {chunk.content_block.name}")
                    current_tool = {
                        "type": "tool_use",
                        "id": chunk.content_block.id,
                        "name": chunk.content_block.name,
                    }
                    logger.debug(f"Starting tool call: {current_tool}")
                else:
                    logger.debug(f"Content block start but not a tool use: {chunk}")
                    if (newline := self._separate_tool_result_from_preceding_text()) and assistant_text == "":
                        # If we have a newline to separate, add it to the assistant text
                        assistant_text += newline
                        logger.debug(
                            f"Adding `{newline}` to start of assistant text (to separate it from previous content block)"
                        )

            elif chunk.type == "content_block_delta":
                if hasattr(chunk.delta, "text"):
                    text = chunk.delta.text
                    assistant_text += text
                    logger.debug(f"Adding text delta: '{text[:20]}...' (truncated)")
                    yield text
                elif getattr(chunk.delta, "type", None) == "citations_delta":
                    # Process citation delta
                    citation = chunk.delta.citation
                    self.citations.append(citation)
                    citation_ref = f" [{len(self.citations)}] "
                    assistant_text += citation_ref
                    logger.debug(f"Adding citation reference: {citation_ref}")
                    yield citation_ref
                elif hasattr(chunk.delta, "partial_json"):
                    # Accumulate JSON for tool arguments
                    current_json += chunk.delta.partial_json
                    logger.debug(f"Accumulating JSON for tool, current length: {len(current_json)}")
                else:
                    logger.debug(f"Unhandled content_block_delta: {chunk.delta}")

            elif chunk.type == "content_block_stop":
                logger.debug("Content block stop received")
                if current_tool:
                    try:
                        logger.debug(f"Parsing accumulated JSON for tool: {current_json[:50]}... (truncated)")
                        arguments = json.loads(current_json)
                        logger.debug(f"Tool arguments: {arguments}")
                        current_tool["input"] = arguments
                        tool_calls.append(current_tool)
                        logger.info(f"Added tool call to queue, total: {len(tool_calls)}")

                        # Reset for next tool
                        current_tool = None
                        current_json = ""

                    except Exception as e:
                        error_msg = f"Tool call failed: {str(e)}"
                        logger.error(error_msg)
                        logger.error(f"Failed JSON: {current_json}")
                        raise

            elif chunk.type == "message_delta":
                message_delta_count += 1
                logger.debug(f"Message delta #{message_delta_count} received")

                if hasattr(chunk.delta, "stop_reason"):
                    logger.debug(f"Message delta has stop_reason: {chunk.delta.stop_reason}")
                    # Both stop reasons need different handling
                    if chunk.delta.stop_reason in ["end_turn", "tool_use"]:
                        if response_finished:
                            stop_reason = chunk.delta.stop_reason
                            logger.warning(f"Received {stop_reason} stop_reason but response already finished - skipping")
                        else:
                            logger.info(f"Message delta has stop_reason {chunk.delta.stop_reason}")

                            if chunk.delta.stop_reason == "end_turn":
                                # For end_turn, create a final assistant message with text and tool calls
                                citations_text = self._finish_response(assistant_text, tool_calls)
                                if citations_text:
                                    yield citations_text

                                # Process any tool calls - the tool use is already in the assistant message
                                try:
                                    self._process_tool_calls(tool_calls)
                                except Exception as e:
                                    logger.error(f"Error in tool call processing: {str(e)}")
                                    # Track in Sentry
                                    if get_settings().SENTRY_DSN:
                                        sentry_sdk.set_tag("error_type", "tool_processing_failure")
                                        sentry_sdk.capture_exception(e)

                            elif chunk.delta.stop_reason == "tool_use" and tool_calls:
                                # For tool_use, we need to create an assistant message with JUST the tool
                                # This is critical to maintain the tool_use -> tool_result relationship
                                logger.info("Adding assistant message with tool_use (no text content)")

                                # Create content blocks with only the tool_use blocks
                                tool_content = []
                                for tc in tool_calls:
                                    tool_content.append(tc)

                                # Add assistant message with just tool_use (no text block)
                                assistant_message = {"role": "assistant", "content": tool_content}

                                # Add to message history
                                self.message_history.append(assistant_message)

                                # For logging, add tool_name
                                log_message = assistant_message.copy()
                                if tool_calls:
                                    log_message["tool_name"] = tool_calls[0]["name"]
                                self._log_message(log_message)

                                # Now process the tool calls
                                try:
                                    self._process_tool_calls(tool_calls)
                                except Exception as e:
                                    logger.error(f"Error in tool call processing: {str(e)}")
                                    # Track in Sentry
                                    if get_settings().SENTRY_DSN:
                                        sentry_sdk.set_tag("error_type", "tool_processing_failure")
                                        sentry_sdk.capture_exception(e)

                            # Mark as finished to prevent duplicate processing
                            response_finished = True
                elif hasattr(chunk.delta, "text"):
                    text = chunk.delta.text
                    assistant_text += text
                    logger.debug(f"Adding message delta text: '{text[:20]}...' (truncated)")
                    yield text
                else:
                    logger.debug(f"Unhandled message_delta: {chunk.delta}")

            elif chunk.type == "message_stop":
                if response_finished:
                    logger.warning("Received message_stop but response already finished - skipping")
                else:
                    logger.info("Message_stop chunk received - finishing response")

                    if assistant_text:
                        # If we have text content, create a complete assistant message with text and tools
                        citations_text = self._finish_response(assistant_text, tool_calls)
                        if citations_text:
                            yield citations_text
                    elif tool_calls:
                        # If we only have tool calls and no text, create an assistant message with JUST tools
                        # This avoids empty text blocks but maintains tool_use -> tool_result relationship
                        logger.info("Creating assistant message with just tool calls (no text)")

                        # Create content with only the tool_use blocks
                        tool_content = []
                        for tc in tool_calls:
                            tool_content.append(tc)

                        # Add assistant message with just tool_use (no text block)
                        assistant_message = {"role": "assistant", "content": tool_content}

                        # Add to message history
                        self.message_history.append(assistant_message)

                        # For logging, add tool_name
                        log_message = assistant_message.copy()
                        log_message["tool_name"] = tool_calls[0]["name"]
                        self._log_message(log_message)

                        # Process the tool calls
                        try:
                            self._process_tool_calls(tool_calls)
                        except Exception as e:
                            logger.error(f"Error in tool call processing: {str(e)}")
                            # Track in Sentry
                            if get_settings().SENTRY_DSN:
                                sentry_sdk.set_tag("error_type", "tool_processing_failure")
                                sentry_sdk.capture_exception(e)

                    response_finished = True

    def _process_tool_calls(self, tool_calls):
        """Process a list of tool calls and add results to message history.

        This is a helper method extracted to avoid code duplication between
        different handlers (tool_use, message_stop, etc.)

        Args:
            tool_calls: List of tool calls to process
        """
        if not tool_calls:
            return

        for tc in tool_calls:
            try:
                # Process the tool call
                (tool_result, reference_list) = self.process_tool_call(tc["name"], tc["input"], tc["id"])

                logger.info(f"Reference list: {json.dumps(reference_list, indent=2)}")

                # Process references - ALWAYS apply special formatting
                document_blocks = []
                if reference_list and len(reference_list) > 0:
                    document_blocks = copy.deepcopy(reference_list)

                    # Always apply special processing for all tools
                    for doc in document_blocks:
                        if "source" in doc and "data" in doc["source"]:
                            try:
                                multilingual_data = parse_multilingual_data(doc["source"]["data"])
                                arabic_text = multilingual_data.get("ar", "")
                                english_text = multilingual_data.get("en", "")

                                text_list = []
                                if arabic_text:
                                    text_list.append(f"Arabic: {arabic_text}")
                                if english_text:
                                    text_list.append(f"English: {english_text}")

                                doc["source"]["data"] = "\n\n".join(text_list)
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse source data to JSON for ref: {doc}")

                # Validation check: If an old "tool_result" message (OF THE SAME TOOL CALL ID)
                # is already appended to self.message_history (from a previous _process_tool_calls() call),
                # then tool result is getting duplicated (i.e., old document_blocks is same as new ones)
                #   so don't append it
                # Corner case: In very rare cases, the old tool_result message will contain a single element in "contents":
                #   "Please see the references below." (i.e., no document_blocks are added).
                #   If so, then (and only then): we append new document_blocks to old "tool_result" message
                # NOTE: We're doing this as Claude's API requires a message history to have
                #   a SINGLE "tool_result" message (i.e., dict) directly after a SINGLE "tool_use" message
                if (
                    (c := self.message_history[-1].get("content"))
                    and isinstance(c, list)
                    and len(c) > 0
                    and c[0].get("type", "") == "tool_result"
                    and c[0].get("tool_use_id", "") == tc["id"]  # <- most important condition check
                ):
                    if len(c) == 1:
                        logger.debug(f"appending {len(document_blocks)} to last tool_result message")
                        self.message_history[-1]["content"].append(document_blocks)
                    else:
                        logger.warning("last message in history is already a 'tool_result' message; Skipping... ")
                    continue
                else:
                    # Add tool result message
                    logger.debug("Adding a 'tool_result' message to history")
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

                # Log the tool result message
                self._log_message(self.message_history[-1])

            except Exception as e:
                logger.error(f"Error processing tool call: {str(e)}")
                # Track tool errors in Sentry
                if get_settings().SENTRY_DSN:
                    sentry_sdk.set_tag("error_type", "tool_call_failure")
                    sentry_sdk.set_tag("tool_name", tc["name"])
                    sentry_sdk.set_context(
                        "tool_details", {"tool_id": tc["id"], "tool_name": tc["name"], "tool_input": tc["input"]}
                    )
                    sentry_sdk.capture_exception(e)

                # Add error as tool result
                error_message = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tc["id"],
                            "content": str(e),
                        }
                    ],
                }
                self.message_history.append(error_message)
                # Log the error message
                self._log_message(self.message_history[-1])

    def _finish_response(self, assistant_text, tool_calls):
        """Handle the completion of a response, adding citations and finalizing the assistant message.

        This method is called when a message completely finishes (not for tool_use pauses).
        It creates an assistant message with the accumulated text and tool calls.
        Called via:
        - message_stop chunk (when there is text content or no tool calls)
        - message_delta with stop_reason 'end_turn'

        Note: For tool_use stop reason, tool calls are processed directly without
        creating an assistant message, avoiding empty text blocks.

        Args:
            assistant_text: The accumulated text from the assistant
            tool_calls: List of tool calls to include in the assistant message

        Returns:
            The citations text that was added, if any, or None
        """
        citations_text = None

        # Add citations list at the end if there were any citations
        if self.citations:
            citations_text = "\n\n**Citations**:\n"
            logger.debug(f"Full Citations: {self.citations}")

            # Process each citation
            for i, citation in enumerate(self.citations, 1):
                cited_text = getattr(citation, "cited_text", "")
                title = getattr(citation, "document_title", "")
                # Title is already trimmed by the search tools, but trim again in case of any direct citations
                title = trim_citation_title(title)
                citations_text += f"[{i}] {title}:\n"

                # First, check if the citation text has already been processed
                if any(lang in cited_text for lang in ["Arabic: ", "English: "]):
                    citations_text += f"{cited_text}\n\n"
                    continue

                # Then, try to parse the citation as a multilingual JSON object
                # This handles cases where Claude cites entire document content (which should be JSON)
                try:
                    # Attempt to parse as JSON
                    multilingual_data = parse_multilingual_data(cited_text)
                    logger.debug(f"Successfully parsed multilingual data: {multilingual_data}")

                    # Extract Arabic and English text
                    arabic_text = multilingual_data.get("ar", "")
                    english_text = multilingual_data.get("en", "")

                    # Add Arabic text if available
                    if arabic_text:
                        citations_text += f" Arabic: {arabic_text}\n\n"

                    # Add English text if available, otherwise translate from Arabic
                    if english_text:
                        citations_text += f" English: {english_text}\n\n"
                    elif arabic_text:
                        english_translation = asyncio.run(translate_texts_parallel([arabic_text], "en", "ar"))[0]
                        citations_text += f" English: {english_translation}\n\n"

                except json.JSONDecodeError:
                    # Handle as plain text (Claude sometimes cites substrings which won't be valid JSON)
                    logger.debug(f"Citation is not valid JSON - treating as plain text: {cited_text[:100]}...")

                    # Try to detect the language and handle accordingly
                    try:
                        # Use the imported function
                        lang = get_language_from_text(cited_text)
                        if lang == "ar":
                            # It's Arabic text
                            arabic_text = cited_text
                            citations_text += f" Arabic: {arabic_text}\n\n"

                            # Translate to English
                            try:
                                english_translation = asyncio.run(translate_texts_parallel([arabic_text], "en", "ar"))[0]
                                citations_text += f" English: {english_translation}\n\n"
                            except Exception as e:
                                logger.error(f"Translation failed: {e}")
                                citations_text += " English: [Translation unavailable]\n\n"
                        else:
                            # It's likely English or other language - just show as is
                            citations_text += f" Text: {cited_text}\n\n"
                    except Exception as e:
                        # If language detection fails, default to treating as English
                        logger.error(f"Language detection failed: {e}")
                        citations_text += f" Text: {cited_text}\n\n"

                except Exception as e:
                    # Log other errors clearly
                    logger.error(f"Citation processing error: {str(e)}")
                    logger.error(f"Raw citation data: {cited_text}")
                    citations_text += f" Text: {cited_text}\n\n"

        # Add the assistant's message to history
        # This is both the text and the tool use calls.
        content_blocks = []

        # Only include text block if there's non-empty text
        assistant_content = assistant_text.strip()

        # If we have citations, append them to the assistant text
        if citations_text:
            # Make sure we have a gap between assistant text and citations
            if assistant_content:
                assistant_content += "\n\n"
            assistant_content += citations_text

        # Add the complete text (assistant text + citations) to content blocks
        if assistant_content:
            content_blocks.append({"type": "text", "text": assistant_content})

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

        logger.debug(f"Adding assistant message to history. Current history length: {len(self.message_history)}")
        logger.debug(f"Assistant message content blocks: {len(message_content)}")

        # Add to message history
        try:
            self.message_history.append(assistant_message)
            logger.debug(f"Successfully added assistant message. New history length: {len(self.message_history)}")
            logger.debug(f"Last message in history role: {self.message_history[-1]['role']}")
        except Exception as e:
            logger.error(f"Failed to append assistant message to history: {str(e)}")
            logger.error(f"assistant_message: {assistant_message}")
            logger.error(f"self.message_history type: {type(self.message_history)}")

        # For logging, create a copy with tool_name for database storage
        if tool_calls:
            logger.debug("Logging assistant message with tool_name")
            log_message = assistant_message.copy()
            log_message["tool_name"] = tool_calls[0]["name"]
            # Log the message with tool_name for database
            self._log_message(log_message)
        else:
            logger.debug("Logging regular assistant message")
            # Log the regular message
            self._log_message(self.message_history[-1])

        # Process any accumulated tool calls
        # Note: This is now handled by the helper method to avoid duplication
        if tool_calls:
            logger.debug(f"Processing {len(tool_calls)} accumulated tool calls")
            try:
                self._process_tool_calls(tool_calls)
            except Exception as e:
                logger.error(f"Error in tool call processing: {str(e)}")
                # Track in Sentry
                if get_settings().SENTRY_DSN:
                    sentry_sdk.set_tag("error_type", "tool_processing_failure")
                    sentry_sdk.capture_exception(e)

        return citations_text

    def limit_documents_in_message_history(self, max_documents=100):
        """
        Limit the total number of document blocks across all messages to prevent Claude from crashing.
        This creates a copy of the message history and modifies the copy, preserving the original data.

        Args:
            max_documents: Maximum number of documents to keep across all messages (default 100)

        Returns:
            A copy of the message history with document count limited to max_documents
        """
        # Create a deep copy of the message history to preserve original data
        limited_history = copy.deepcopy(self.message_history)

        # Count and collect all document blocks
        all_documents = []

        # First, collect all document blocks with their positions in the message history
        for msg_idx, msg in enumerate(limited_history):
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                # Find document blocks in this message
                for block_idx, block in enumerate(msg["content"]):
                    if isinstance(block, dict) and block.get("type") == "document":
                        # Store document with its position for later removal if needed
                        all_documents.append({"document": block, "position": (msg_idx, block_idx)})

        document_count = len(all_documents)
        logger.debug(f"Found {document_count} document blocks in message history")

        # If we have more documents than allowed, remove the oldest ones
        if document_count > max_documents:
            logger.warning(f"Limiting documents from {document_count} to {max_documents}")

            # Calculate how many documents to remove
            documents_to_remove = document_count - max_documents

            # Sort by position - earliest messages first (these will be removed)
            all_documents.sort(key=lambda x: x["position"][0])

            # Get the positions of documents to remove
            positions_to_remove = [doc["position"] for doc in all_documents[:documents_to_remove]]

            # Now remove documents from the copy of the message history
            # We need to process messages in reverse order to avoid index shifting
            positions_by_message = {}
            for msg_idx, block_idx in positions_to_remove:
                if msg_idx not in positions_by_message:
                    positions_by_message[msg_idx] = []
                positions_by_message[msg_idx].append(block_idx)

            # For each message, remove blocks in reverse order
            for msg_idx in sorted(positions_by_message.keys()):
                block_indices = sorted(positions_by_message[msg_idx], reverse=True)

                # Get the message content
                if isinstance(limited_history[msg_idx].get("content"), list):
                    for block_idx in block_indices:
                        # Remove this document block
                        logger.debug(f"Removing document block at position {msg_idx},{block_idx}")
                        if block_idx < len(limited_history[msg_idx]["content"]):
                            limited_history[msg_idx]["content"].pop(block_idx)

        return limited_history

    def process_message_history(self, use_tool=True):
        """
        This is the main loop that processes the message history.
        It yields from the process_one_round method until the last message is an assistant message.
        The assumption coming in to this is that it ends with a user message.
        """
        logger.info("Starting process_message_history")
        logger.debug(f"Initial message history length: {len(self.message_history)}")

        if len(self.message_history) > 0:
            logger.debug(f"Last message role: {self.message_history[-1]['role']}")
            last_role = self.message_history[-1]["role"]
            if last_role == "assistant":
                logger.info("Message history already ends with assistant message, no processing needed")

        count = 0
        # Store the previous state of the entire message history for simple comparison
        prev_history_json = json.dumps(self.message_history)

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

        logger.debug(f"Starting message processing loop with history length: {len(self.message_history)}")
        if len(self.message_history) > 0:
            logger.debug(f"Last message role before loop: {self.message_history[-1]['role']}")
        else:
            logger.warning("Message history is empty before processing loop")

        # Add a max_iterations limit to prevent infinite loops
        max_iterations = 10  # Reasonable upper limit based on expected conversation flow
        while len(self.message_history) > 0 and self.message_history[-1]["role"] != "assistant" and count < max_iterations:
            logger.info(f"Processing message iteration: {count}")
            logger.debug("Current message history:\n" + "-" * 60)
            for i, msg in enumerate(self.message_history):
                logger.debug(f"Message {i}:\n{json.dumps(msg, indent=2)}")
            logger.debug("-" * 60)

            # This is pretty complicated so leaving a comment.
            # We want to yield from so that we can send the sequence through the input
            # Also use tools only if we haven't tried too many times (failure)
            #  and if the last message was not from the tool (success!)
            logger.debug("Calling process_one_round()")

            try:
                yield from self.process_one_round()
                logger.debug(f"After process_one_round(), message history length: {len(self.message_history)}")

                # Simple check - compare entire message history with previous state
                current_history_json = json.dumps(self.message_history)

                # Check if message_history is identical to previous iteration
                if current_history_json == prev_history_json:
                    logger.warning("Message history hasn't changed since last iteration - loop detected!")

                    # Add a text-only message indicating the loop
                    self.message_history.append(
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "I got stuck in a loop. Please rephrase your question."}],
                        }
                    )
                    # Log this message
                    self._log_message(self.message_history[-1])
                    # Break out of the loop
                    break

                # Update previous state for next iteration comparison
                prev_history_json = current_history_json

                if len(self.message_history) > 0:
                    logger.debug(f"Last message role after process_one_round: {self.message_history[-1]['role']}")
                else:
                    logger.warning("Message history is empty after process_one_round!")
            except Exception as e:
                logger.error(f"Error in process_one_round: {str(e)}")
                # Track in Sentry
                if get_settings().SENTRY_DSN:
                    sentry_sdk.set_tag("error_type", "process_round_failure")
                    sentry_sdk.capture_exception(e)

                # Add an error message to the conversation
                error_message = {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "I encountered a problem processing your request. "
                            + "Please try again or rephrase your question.",
                        }
                    ],
                }
                self.message_history.append(error_message)
                self._log_message(error_message)
                # Don't raise - log and continue to avoid breaking the loop

            count += 1
            logger.debug(f"Completed iteration {count} of message processing")

        # Log the final state after processing completes
        logger.info(f"Finished process_message_history after {count} iterations")
        logger.debug(f"Final message history length: {len(self.message_history)}")

        # Check if we hit the iteration limit
        if count >= max_iterations:
            logger.warning(f"Hit max iterations limit ({max_iterations}). Check for processing issues.")

        if len(self.message_history) > 0:
            logger.info(f"Final message role: {self.message_history[-1]['role']}")
            if self.message_history[-1]["role"] != "assistant":
                logger.warning("Processing completed but final message is not from assistant!")
        else:
            logger.warning("Processing completed but message history is empty!")
