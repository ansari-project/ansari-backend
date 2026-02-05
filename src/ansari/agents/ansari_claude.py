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
from ansari.util.robust_translation import parse_multilingual_data, process_document_source_data
from ansari.util.translation import translate_texts_parallel
from ansari.util.general_helpers import get_language_from_text, trim_citation_title

# Set up logging
logger = get_logger(__name__)


class AnsariClaude(Ansari):
    """Claude-based implementation of the Ansari agent."""

    def __init__(self, settings: Settings, message_logger: MessageLogger = None, json_format=False, system_prompt_file=None):
        """Initialize the Claude-based Ansari agent.

        Args:
            settings: Application settings
            message_logger: Optional message logger instance
            json_format: Whether to use JSON format for responses
            system_prompt_file: Optional system prompt file name (defaults to 'system_msg_claude')
        """
        # Call parent initialization
        super().__init__(settings, message_logger, json_format)

        # Set the system prompt file to use (can be overridden for specific use cases like ayah endpoint)
        self.system_prompt_file = system_prompt_file or "system_msg_claude"

        # Log environment information for debugging
        try:
            import anthropic
            import sys
            import platform

            logger.debug(f"Python version: {sys.version}")
            logger.debug(f"Platform: {platform.platform()}")
            logger.debug(f"Anthropic client version: {anthropic.__version__}")

            # Log API key configuration (safely)
            api_key_status = "Set" if hasattr(settings, "ANTHROPIC_API_KEY") and settings.ANTHROPIC_API_KEY else "Not set"
            logger.debug(f"ANTHROPIC_API_KEY status: {api_key_status}")

            # Log model configuration
            logger.debug(f"Using model: {settings.ANTHROPIC_MODEL}")
        except Exception as e:
            logger.error(f"Error logging environment info: {str(e)}")

        # Initialize Claude-specific client with prompt caching support
        try:
            self.client = anthropic.Anthropic(default_headers={"anthropic-beta": "prompt-caching-2024-07-31"})
            logger.debug("Successfully initialized Anthropic client with prompt caching support")
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

        # Initialize tool usage tracking
        self.tool_usage_history = []
        # Track historical tool calls with their parameters
        self.tool_calls_with_args = []

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
            logger.debug("No message_logger available, skipping message logging")
            return

        # Validate message structure
        if not self.validate_message(message):
            logger.warning(f"Invalid message structure: {message}")
            return

        logger.debug(f"Logging {message}")
        try:
            self.message_logger.log(message)
            logger.debug(f"Successfully logged message with role: {message['role']}")
        except Exception as e:
            logger.error(f"Error logging message: {str(e)}")
            logger.error(f"Message that failed to log: {message}")

    def process_input(self, user_input: str):
        """Process user input and generate a response."""
        logger.debug(f"Processing input: {user_input}")

        # Reset tool usage history for each new conversation
        self.tool_usage_history = []
        self.tool_calls_with_args = []
        logger.debug("Reset tool usage history for new conversation")

        # Call parent implementation to process the input
        for m in super().process_input(user_input):
            if m:
                yield m

    def replace_message_history(self, message_history: list[dict], use_tool=True, stream=True):
        """
        Replaces the current message history (stored in Ansari) with the given message history,
        and then processes it to generate a response from Ansari.
        """
        # Reset tool usage history for each message history replacement
        self.tool_usage_history = []
        self.tool_calls_with_args = []
        logger.debug("Reset tool usage history for message history replacement")
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

    def _validate_message_history(self):
        """
        Perform pre-flight validation of message history to prevent Claude API errors.

        This method:
        1. Ensures all tool_use blocks have matching tool_result blocks
        2. Ensures all tool_result blocks have at least one document block
        3. Ensures tool_use/tool_result pairs appear in the correct sequence

        Side effect:
            May modify self.message_history by adding missing tool_result blocks
            or document blocks to ensure API compatibility.
        """
        # First check if we need any repairs at all
        needs_repair = False

        # Count tool_use blocks without matching tool_result blocks
        tool_use_ids = set()
        tool_result_ids = set()

        # Collect all tool_use IDs
        for msg in self.message_history:
            if msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and "id" in block:
                        tool_use_ids.add(block["id"])

        # Collect all tool_result IDs
        for msg in self.message_history:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result" and "tool_use_id" in block:
                        tool_result_ids.add(block["tool_use_id"])

        # Check for missing tool_result blocks
        missing_results = tool_use_ids - tool_result_ids
        if missing_results:
            logger.warning(f"Found {len(missing_results)} tool_use blocks without matching tool_result blocks")
            needs_repair = True

        # Check for tool_result blocks without document blocks
        for msg in self.message_history:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        # Skip error tool_results — they intentionally have no documents
                        if block.get("is_error"):
                            continue
                        # Skip tool_results with no content — valid for no-results cases
                        if "content" not in block:
                            continue
                        # Check for documents as siblings (old format) or
                        # nested inside tool_result.content (current format)
                        has_document = any(isinstance(b, dict) and b.get("type") == "document" for b in msg["content"])
                        if not has_document:
                            tool_content = block.get("content", [])
                            if isinstance(tool_content, list):
                                has_document = any(
                                    isinstance(item, dict) and item.get("type") == "document" for item in tool_content
                                )
                        if not has_document:
                            logger.warning(f"Found tool_result without document block: {block.get('tool_use_id')}")
                            needs_repair = True
                            break

        # If any issue was found, do a full repair
        if needs_repair:
            logger.debug("Repairing message history before sending to Claude API")
            self._fix_tool_use_result_relationship()

    def _check_tool_limit(self, current_tool_name, current_tool_args=None):
        """
        Check if adding the current tool would exceed our tool usage limits.

        This method checks two conditions:
        1. If adding this tool would make 4 consecutive uses of the same tool
        2. If adding this tool would exceed 5 total tool calls

        Args:
            current_tool_name: The name of the tool about to be used
            current_tool_args: Optional arguments for the current tool

        Returns:
            bool: True if a limit would be reached, False otherwise
        """
        # If no tool usage yet, no limit reached
        if not self.tool_usage_history:
            return False

        # Check for same tool used consecutively 4 times (including the current one)
        if len(self.tool_usage_history) >= 3:
            last_three_tools = self.tool_usage_history[-3:]
            if last_three_tools[0] == last_three_tools[1] == last_three_tools[2] == current_tool_name:
                logger.warning(f"Adding {current_tool_name} would make 4 consecutive uses - limit would be reached")
                # Log all tool usages and their parameters
                logger.warning(f"Tool usage history: {self.tool_usage_history}")
                # Log detailed information about each tool call
                for i, call in enumerate(self.tool_calls_with_args):
                    logger.warning(f"Tool call #{i + 1}: {call['tool']} - Args: {call['args']} - ID: {call['tool_id']}")
                return True

        # Check if adding this tool would exceed 10 total calls
        if len(self.tool_usage_history) >= 9:
            logger.warning(f"Adding {current_tool_name} would exceed total tool usage limit of 10")
            # Log all tool usages and their parameters
            logger.warning(f"Tool usage history: {self.tool_usage_history}")
            # Log detailed information about each tool call
            for i, call in enumerate(self.tool_calls_with_args):
                logger.warning(f"Tool call #{i + 1}: {call['tool']} - Args: {call['args']} - ID: {call['tool_id']}")
            return True

        return False

    def _force_answer_on_tool_limit(self):
        """
        Check if tool usage has hit limits and force Claude to provide a final answer if needed.

        This method checks for:
        1. Same tool used consecutively 3+ times
        2. Total tool usage exceeds 10 calls

        Returns:
            bool: True if a limit was reached and intervention was applied, False otherwise
        """
        # If no tool usage yet, no need to check
        if not self.tool_usage_history:
            return False

        # Check for same tool used consecutively 3+ times
        if len(self.tool_usage_history) >= 3:
            last_three_tools = self.tool_usage_history[-3:]
            if last_three_tools[0] == last_three_tools[1] == last_three_tools[2]:
                tool_name = last_three_tools[0]
                logger.warning(f"Same tool '{tool_name}' used 3 times consecutively - forcing answer")

                # Add a message forcing Claude to provide a final answer
                force_answer_message = {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "You've used the same search tool multiple times. Please stop searching and "
                                "provide a complete answer based on the information you have. "
                                "Format your answer properly with the information you've gathered so far."
                            ),
                        }
                    ],
                }

                self.message_history.append(force_answer_message)
                self._log_message(force_answer_message)
                return True

        # Check for total tool usage exceeding 10 calls
        if len(self.tool_usage_history) >= 10:
            logger.warning("Total tool usage exceeded limit (10) - forcing answer")

            # Add a message forcing Claude to provide a final answer
            force_answer_message = {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "You've made multiple tool calls. Please stop using tools and "
                            "provide a complete answer based on the information you have. "
                            "Format your answer properly with the information you've gathered so far."
                        ),
                    }
                ],
            }

            self.message_history.append(force_answer_message)
            self._log_message(force_answer_message)
            return True

        return False

    def process_tool_call(self, tool_name: str, tool_args: dict, tool_id: str):
        """Process a tool call and return its result as a list."""
        # Check if we need to force an answer due to tool usage patterns BEFORE tracking this tool
        # This prevents counting the current tool if we're already at the limit
        if self._check_tool_limit(tool_name, tool_args):
            tool_limit_message = (
                "Tool usage limit reached. Please synthesize a complete answer "
                "based on the information you've already gathered, maintaining any requested format."
            )
            logger.warning(f"Tool usage limit reached: {tool_limit_message}")

            # Return as error tuple: (message, None, is_error=True)
            # Using is_error flag avoids citation consistency issues with document blocks
            return (tool_limit_message, None, True)

        # If we didn't hit the limit, track tool usage now
        self.tool_usage_history.append(tool_name)
        # Also track the tool arguments
        self.tool_calls_with_args.append({"tool": tool_name, "args": tool_args, "tool_id": tool_id})
        logger.debug(f"Tool usage history: {self.tool_usage_history}")

        if tool_name not in self.tool_name_to_instance:
            logger.warning(f"Unknown tool name: {tool_name}")
            error_message = f"Unknown tool: {tool_name}"
            # Return as error tuple to avoid citation consistency issues
            return (error_message, None, True)

        try:
            query = tool_args["query"]  # tool_args is now a dict, not a string
        except KeyError as e:  # Remove JSONDecodeError since we're not parsing JSON
            logger.error(f"Failed to parse tool arguments: {e}")
            logger.error(f"Raw arguments: {tool_args}")
            error_message = f"Invalid tool arguments: {str(e)}"
            # Return as error tuple to avoid citation consistency issues
            return (error_message, None, True)

        try:
            tool_instance = self.tool_name_to_instance[tool_name]

            # Get raw results
            results = tool_instance.run(query)

            # Format results in different ways
            tool_result = tool_instance.format_as_tool_result(results)
            reference_list = tool_instance.format_as_ref_list(results)

            # Check for empty results - possibly due to rate limiting
            if not reference_list:
                logger.warning(f"No results returned for {tool_name} with query '{query}'. Possible rate limiting.")
                error_message = (
                    "No results found for this query. This might be due to rate limiting "
                    "if multiple searches were performed in quick succession."
                )
                # Return as error tuple to avoid citation consistency issues
                return (error_message, None, True)

            logger.debug(f"Got {len(reference_list)} results from {tool_name}")

            # Return results
            return (tool_result, reference_list)

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {str(e)}")
            error_message = f"Error executing search: {str(e)}"
            # Return as error tuple to avoid citation consistency issues
            return (error_message, None, True)

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
            and isinstance(content, list)
            and len(content) > 0
            and isinstance(content[0], dict)
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
        system_prompt = prompt_mgr.bind(self.system_prompt_file).render()

        # Run pre-flight validation to ensure proper tool_use/tool_result relationship
        # This helps prevent API errors by fixing message structure before sending
        self._validate_message_history()

        # Log the final message history before sending to API
        logger.debug(f"Sending messages to Claude: {json.dumps(self.message_history, indent=2)}")

        # Limit documents in message history to prevent Claude from crashing
        # This creates a copy of the message history, preserving the original
        limited_history = self.limit_documents_in_message_history(max_documents=100)

        # Add cache control to ONLY the LAST content block of the last message for prompt caching optimization
        if limited_history and len(limited_history) > 0:
            last_message = limited_history[-1]
            # Add cache control only to the LAST content block in the last message
            if isinstance(last_message.get("content"), list) and len(last_message["content"]) > 0:
                # Only add to the last block
                last_block = last_message["content"][-1]
                if isinstance(last_block, dict):
                    # Add ephemeral cache control to only the last content block
                    last_block["cache_control"] = {"type": "ephemeral"}
                logger.debug(
                    f"Added ephemeral cache control to last content block of last message "
                    f"with role: {last_message.get('role')}"
                )
            elif isinstance(last_message.get("content"), str):
                # If content is a string, convert to list format with cache control
                last_message["content"] = [
                    {"type": "text", "text": last_message["content"], "cache_control": {"type": "ephemeral"}}
                ]
                logger.debug(
                    f"Converted string content to list format with cache control for role: {last_message.get('role')}"
                )

        # Create API request parameters with the limited history
        params = {
            "model": self.settings.ANTHROPIC_MODEL,
            "system": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
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
        logger.debug(f"API request parameters: {logger_params}")

        failures = 0
        response = None
        start_time = time.time()

        # Retry loop for API calls
        while not response:
            try:
                logger.debug("Calling Anthropic API...")
                response = self.client.messages.create(**params)
                elapsed = time.time() - start_time
                logger.debug(f"API connection established after {elapsed:.2f}s")
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
                    logger.debug(f"Dumped message history to {json_file_path}")

                if failures >= self.settings.MAX_FAILURES:
                    logger.error("Max retries exceeded")
                    raise

                logger.debug("Retrying in 5 seconds...")
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

        logger.debug("Processing response chunks")

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
                    logger.debug(f"Starting tool call with id: {chunk.content_block.id}, name: {chunk.content_block.name}")
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
                        logger.debug(f"Added tool call to queue, total: {len(tool_calls)}")

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
                            logger.debug(f"Message delta has stop_reason {chunk.delta.stop_reason}")

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
                                logger.debug("Adding assistant message with tool_use (no text content)")

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
                    logger.debug("Received message_stop but response already finished - skipping")
                else:
                    logger.debug("Message_stop chunk received - finishing response")

                    if assistant_text:
                        # If we have text content, create a complete assistant message with text and tools
                        citations_text = self._finish_response(assistant_text, tool_calls)
                        if citations_text:
                            yield citations_text
                    elif tool_calls:
                        # If we only have tool calls and no text, create an assistant message with JUST tools
                        # This avoids empty text blocks but maintains tool_use -> tool_result relationship
                        logger.debug("Creating assistant message with just tool calls (no text)")

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

    def _fix_tool_use_result_relationship(self):
        """
        Fix missing or misaligned tool_use and tool_result blocks in the message history.
        This method ensures that every tool_use has a corresponding tool_result with at least
        one document block, and that they appear in the correct sequence.

        Side effect:
            - May modify self.message_history directly
        """
        logger.warning("Fixing tool_use/tool_result relationship issues in message history")

        # 1. First identify all tool_use blocks and their locations
        tool_use_info = {}  # Maps tool ID to (message_idx, block) pairs
        for msg_idx, msg in enumerate(self.message_history):
            if msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and "id" in block:
                        tool_id = block["id"]
                        tool_use_info[tool_id] = (msg_idx, block)
                        logger.debug(f"Found tool_use block with ID {tool_id} at message index {msg_idx}")

        # 2. Check which tool_use IDs have corresponding tool_result blocks
        tool_result_info = {}  # Maps tool ID to message_idx
        for msg_idx, msg in enumerate(self.message_history):
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result" and "tool_use_id" in block:
                        tool_id = block["tool_use_id"]
                        tool_result_info[tool_id] = msg_idx
                        logger.debug(f"Found tool_result block with ID {tool_id} at message index {msg_idx}")

        # 3. Create fallback tool_result blocks for any tool_use without a result
        for tool_id, (msg_idx, tool_block) in tool_use_info.items():
            if tool_id not in tool_result_info:
                logger.warning(f"Adding missing tool_result for tool_use ID {tool_id}")

                # Create a fallback tool_result message with no content
                fallback_result = {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": tool_id},
                    ],
                }

                # Insert it immediately after the tool_use message
                self.message_history.insert(msg_idx + 1, fallback_result)
                logger.debug(f"Added fallback tool_result for ID {tool_id} after message {msg_idx}")

                # Update the tool_result_info map with the new position
                tool_result_info[tool_id] = msg_idx + 1

                # Update indices for any subsequent tool_use/result messages
                for other_id, (other_idx, other_block) in list(tool_use_info.items()):
                    if other_idx > msg_idx:
                        tool_use_info[other_id] = (other_idx + 1, other_block)

                for other_id, other_idx in list(tool_result_info.items()):
                    if other_id != tool_id and other_idx > msg_idx:
                        tool_result_info[other_id] = other_idx + 1

        # 4. Remove any invalid tool_result blocks (those without matching tool_use)
        invalid_result_indices = []
        for msg_idx, msg in enumerate(self.message_history):
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for block_idx, block in enumerate(msg["content"]):
                    if isinstance(block, dict) and block.get("type") == "tool_result" and "tool_use_id" in block:
                        tool_id = block["tool_use_id"]
                        if tool_id not in tool_use_info:
                            logger.warning(f"Found tool_result with ID {tool_id} but no matching tool_use block")
                            invalid_result_indices.append((msg_idx, block_idx))

        # Remove the invalid blocks (if any)
        removed_messages = set()  # Track which messages we've removed
        for msg_idx, block_idx in sorted(invalid_result_indices, reverse=True):
            if msg_idx in removed_messages:
                continue  # Skip if we've already removed this message

            # For simplicity, just remove the entire message if it's just a tool_result
            if len(self.message_history[msg_idx]["content"]) <= 2:  # tool_result + maybe a document
                logger.warning(f"Removing invalid tool_result message at index {msg_idx}")
                self.message_history.pop(msg_idx)
                removed_messages.add(msg_idx)

                # Update indices for all tool use/result locations
                for tool_id, (use_idx, block) in list(tool_use_info.items()):
                    if use_idx > msg_idx:
                        tool_use_info[tool_id] = (use_idx - 1, block)

                for tool_id, result_idx in list(tool_result_info.items()):
                    if result_idx > msg_idx:
                        tool_result_info[tool_id] = result_idx - 1
            else:
                # Otherwise just remove the specific tool_result block
                logger.warning(f"Removing invalid tool_result block from message {msg_idx}")
                self.message_history[msg_idx]["content"].pop(block_idx)

        # 5. Final check - ensure tool_results are placed immediately after their tool_use blocks
        for tool_id, (use_idx, _) in tool_use_info.items():
            if tool_id in tool_result_info:
                result_idx = tool_result_info[tool_id]

                # If the result doesn't immediately follow the use, move it
                if result_idx != use_idx + 1:
                    logger.warning(
                        f"Tool_result for ID {tool_id} is at wrong position (found at {result_idx}, should be {use_idx + 1})"
                    )

                    # Skip if the message was already removed
                    if result_idx in removed_messages:
                        continue

                    # Get the result message
                    result_msg = self.message_history.pop(result_idx)

                    # Adjust indices if the result was before the use
                    if result_idx < use_idx:
                        use_idx -= 1

                    # Insert at the correct position
                    self.message_history.insert(use_idx + 1, result_msg)
                    logger.debug(f"Moved tool_result for ID {tool_id} to position {use_idx + 1}")

                    # Update the tool_result_info map
                    tool_result_info[tool_id] = use_idx + 1

        logger.debug("Completed tool_use/tool_result relationship fix")

    def _process_tool_calls(self, tool_calls):
        """Process a list of tool calls and add results to message history.

        This is a helper method extracted to avoid code duplication between
        different handlers (tool_use, message_stop, etc.)

        IMPORTANT: All tool results are consolidated into a SINGLE user message.
        The Anthropic API requires that all tool_results for tool_uses in one
        assistant message must appear in the same user message immediately after.

        Args:
            tool_calls: List of tool calls to process
        """
        if not tool_calls:
            return

        # Collect all tool results into a single content array
        all_tool_result_content = []

        for tc in tool_calls:
            try:
                # Process the tool call
                result = self.process_tool_call(tc["name"], tc["input"], tc["id"])

                # Check if this is an error return (3-tuple) vs success (2-tuple)
                if len(result) == 3:
                    # Error case: (message, None, is_error)
                    error_message, _, _ = result
                    logger.debug(f"Tool {tc['name']} returned error: {error_message}")
                    all_tool_result_content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tc["id"],
                            "content": error_message,
                            "is_error": True,
                        }
                    )
                    continue  # Skip document processing for errors

                # Success case: (tool_result, reference_list)
                tool_result, reference_list = result
                logger.debug(f"Reference list: {json.dumps(reference_list, indent=2)}")

                # Process references - ALWAYS apply special formatting
                document_blocks = []
                if reference_list and len(reference_list) > 0:
                    document_blocks = copy.deepcopy(reference_list)

                    # Always apply special processing for all tools
                    for doc in document_blocks:
                        if "source" in doc and "data" in doc["source"]:
                            # Use the robust document processing function
                            processed_doc = process_document_source_data(doc)

                            # Update the document with the processed version
                            doc.update(processed_doc)

                # If no document blocks, return empty tool_result (no content field needed)
                if not document_blocks:
                    logger.warning(f"No document blocks found for tool {tc['name']} - returning empty tool_result")
                    all_tool_result_content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tc["id"],
                        }
                    )
                else:
                    # Add tool_result with document blocks INSIDE content (per Anthropic API spec)
                    tool_result_content = [{"type": "text", "text": "Please see the references below."}]
                    tool_result_content.extend(document_blocks)

                    all_tool_result_content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tc["id"],
                            "content": tool_result_content,
                        }
                    )

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

                # Add error as tool result with is_error flag
                all_tool_result_content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "is_error": True,
                    }
                )

        # Add ONE consolidated user message with all tool results
        if all_tool_result_content:
            logger.debug(f"Adding consolidated tool_result message with {len(tool_calls)} tool results")
            consolidated_message = {
                "role": "user",
                "content": all_tool_result_content,
            }
            self.message_history.append(consolidated_message)
            self._log_message(consolidated_message)

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
                        english_translations = self._translate_with_event_loop_safety([arabic_text], "citation processing")
                        english_translation = english_translations[0]
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
                                english_translations = self._translate_with_event_loop_safety(
                                    [arabic_text], "plain text citation"
                                )
                                english_translation = english_translations[0]
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
            # If no content blocks, use a fallback non-empty text element
            # Claude API requires text content blocks to be non-empty
            message_content = [{"type": "text", "text": "I'm processing your request."}]

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

    def _translate_with_event_loop_safety(self, arabic_texts: list[str], context: str = "citation") -> list[str]:
        """
        Safely translate multiple Arabic texts to English, handling both event loop contexts.

        This helper function first tries to use asyncio.run() for parallel translation,
        and falls back to sequential synchronous processing if already in an event loop.

        Args:
            arabic_texts: List of Arabic texts to translate
            context: Description of the context for logging (e.g., "citation", "plain text citation")

        Returns:
            List of English translations
        """
        if not arabic_texts:
            return []

        try:
            # First try to use asyncio.run() (works when not in event loop)
            logger.info(f"Attempting parallel translation using asyncio.run() for {context}")
            return asyncio.run(translate_texts_parallel(arabic_texts, "en", "ar"))
        except RuntimeError as e:
            # If we get RuntimeError, we're already in an event loop,
            # so we're most likely running this function from a BackgroundTask in WhatsApp
            # (so we can't create a new event loop, as we're already inside one!)
            # Side NOTE: Currently, `_finish_response()` calls this function with `len(arabic_texts)==1`
            #   So we won't see a performance difference, but in the future, we should either write code here
            #   to send `translate_text()` to different processes (unstable), OR to make all the callers `async def` functions
            #   which is a major code change, OR find alternative to `BackgroundTasks` in whatsapp logic
            logger.info(f"asyncio.run() failed ({e}), using sequential translation to avoid complexity")
            from ansari.util.translation import translate_text

            results = []
            for text in arabic_texts:
                result = translate_text(text, "en", "ar")
                results.append(result)
            return results

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
        logger.debug("Starting process_message_history")
        logger.debug(f"Initial message history length: {len(self.message_history)}")

        if len(self.message_history) > 0:
            logger.debug(f"Last message role: {self.message_history[-1]['role']}")
            last_role = self.message_history[-1]["role"]
            if last_role == "assistant":
                logger.debug("Message history already ends with assistant message, no processing needed")

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

        # Sanitize tool_result.content: fix existing DB records where tools returned
        # ["No results found."] (bare string) instead of [].
        for msg in self.message_history:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_content = block.get("content", [])
                        if isinstance(tool_content, list) and "No results found." in tool_content:
                            logger.warning(
                                f"Removing tool_result.content containing 'No results found.' for {block.get('tool_use_id')}"
                            )
                            del block["content"]

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
            logger.debug(f"Processing message iteration: {count}")
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
        logger.debug(f"Finished process_message_history after {count} iterations")
        logger.debug(f"Final message history length: {len(self.message_history)}")

        # Check if we hit the iteration limit
        if count >= max_iterations:
            logger.warning(f"Hit max iterations limit ({max_iterations}). Check for processing issues.")

        if len(self.message_history) > 0:
            logger.debug(f"Final message role: {self.message_history[-1]['role']}")
            if self.message_history[-1]["role"] != "assistant":
                logger.warning("Processing completed but final message is not from assistant!")
        else:
            logger.warning("Processing completed but message history is empty!")
