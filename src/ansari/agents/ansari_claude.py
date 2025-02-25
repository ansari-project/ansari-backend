import json
import logging
import time
import traceback
from datetime import datetime
from typing import Generator

import anthropic
from anthropic.types import ContentBlock, Message

from ansari.agents.ansari import Ansari
from ansari.ansari_db import MessageLogger
from ansari.config import Settings
from ansari.util.prompt_mgr import PromptMgr
from ansari.tools.search_hadith import SearchHadith
from ansari.tools.search_quran import SearchQuran
from ansari.tools.search_vectara import SearchVectara
<<<<<<< HEAD
from ansari.ansari_logger import get_logger
=======
>>>>>>> f67369c (Fixed each of the sources.)
from pprint import pformat

# Set up logging
logger = get_logger()


class AnsariClaude(Ansari):
    """Claude-based implementation of the Ansari agent."""
    
    def __init__(self, settings: Settings, message_logger: 
        MessageLogger = None, json_format=False):
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
            
        role = message["role"]
        content = message["content"]
        
        # Ensure consistent structure before storing
        if role == "assistant" and not isinstance(content, list):
            logger.warning(f"Assistant message with non-list content: {content}")
            # Convert to standard format
            content = [{"type": "text", "text": str(content)}]
        
        # Initialize variables for tracking tool and reference information
        tool_name = None
        tool_details = None
        ref_list = None
        
        # Handle different message content formats
        if isinstance(content, list):
            # Extract tool use information from assistant messages
            tool_use_blocks = [block for block in content if block.get("type") == "tool_use"]
            if tool_use_blocks and role == "assistant":
                tool_block = tool_use_blocks[0]  # Use first tool if multiple
                
                # Ensure tool block has all required fields
                if "id" not in tool_block or "name" not in tool_block or "input" not in tool_block:
                    logger.warning(f"Tool use block missing required fields: {tool_block}")
                else:
                    tool_name = tool_block.get("name")
                    tool_details = {
                        "id": tool_block.get("id"),
                        "input": tool_block.get("input")
                    }
                    
                    # Filter out tool use blocks for content storage
                    # We'll reconstruct them during retrieval
                    filtered_content = [block for block in content if block.get("type") != "tool_use"]
                    if filtered_content:
                        content = filtered_content
                    else:
                        # Ensure we don't store empty content if all blocks were tool use
                        content = [{"type": "text", "text": ""}]
            
            # Extract reference lists from user messages containing tool results
            tool_result_blocks = [block for block in content if block.get("type") == "tool_result"]
            if tool_result_blocks and role == "user":
                # Ensure tool result blocks have required fields
                for block in tool_result_blocks:
                    if "tool_use_id" not in block:
                        logger.warning(f"Tool result block missing tool_use_id: {block}")
                    if "content" not in block:
                        logger.warning(f"Tool result block missing content: {block}")
                        # Add default content
                        block["content"] = "No content available"
                
                # Separate reference documents (documents with type field) from the tool result
                ref_blocks = [block for block in content if block.get("type") == "document"]
                other_blocks = [block for block in content if block.get("type") != "document"]
                
                if ref_blocks:
                    # Ensure each reference block has required fields
                    for block in ref_blocks:
                        if not isinstance(block, dict) or "type" not in block:
                            logger.warning(f"Reference block missing type field: {block}")
                    
                    ref_list = ref_blocks
                    content = other_blocks  # Store only the non-reference blocks in content
                    
                    # Ensure we don't store empty content
                    if not content:
                        content = [{"type": "text", "text": ""}]
        
        # Log the message with appropriate structure
        self.message_logger.log(
            role=role,
            content=content,
            tool_name=tool_name,
            tool_details=tool_details,
            ref_list=ref_list
        )

    def replace_message_history(self, message_history: list[dict], use_tool=True, stream=True):
        """
        Replaces the current message history (stored in Ansari) with the given message history,
        and then processes it to generate a response from Ansari.
        """
        # AnsariClaude doesn't use system message, so we don't need to prefix it
        self.message_history = message_history

        for m in self.process_message_history(use_tool, stream=stream):
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
            "input_schema": tool["function"]["parameters"]
        }

    def process_tool_call(self, tool_name: str, tool_args: str, tool_id: str):
        """Process a tool call and return its result as a list."""
        if tool_name not in self.tool_name_to_instance:
            logger.warning(f"Unknown tool name: {tool_name}")
            return []
            
        try:
            arguments = json.loads(tool_args)
            query = arguments["query"]
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse tool arguments: {e}")
            logger.error(f"Raw arguments: {tool_args}")
            raise

        tool_instance = self.tool_name_to_instance[tool_name]
        
        # Get raw results
        results = tool_instance.run(query)
        
        # Format results in different ways
        tool_result = tool_instance.format_as_tool_result(results)
        reference_list = tool_instance.format_as_reference_list(results)
        
        if not reference_list:
            return ["No results found"]
            
        logger.info(f"Got {len(reference_list)} results from {tool_name}")
        
        # Add reference list to tool result
       
        return (tool_result, reference_list)

    def process_one_round(self, use_tool=True, stream=True) -> Generator[str, None, None]:
        """Process one round of conversation.
        
        Args:
            use_tool: Whether to allow tool usage. Intended to be used when using a tool fails. 
            stream: Whether to stream the response
            
        Yields:
            Chunks of the response text

        Side effect: 
            - Updates the message history with at most one assistant message and one user message
            - Logs these messages once they're complete
        """
        prompt_mgr = PromptMgr()
        system_prompt = prompt_mgr.bind("system_msg_claude").render()

        logger.info(f"Sending messages to Claude: {self.message_history}")
        
        # Create API request parameters
        params = {
            "model": self.settings.ANTHROPIC_MODEL,
            "system": system_prompt,
            "messages": self.message_history,
            "max_tokens": 4096,
            "temperature": 0.0,
            "stream": stream
        }

        # Add tools if enabled or if history contains tool messages
        has_tool_messages = any(
            any(c.get("type") in ["tool_use", "tool_result"] for c in msg.get("content", []))
            if isinstance(msg.get("content"), list) else False
            for msg in self.message_history
        )
        if use_tool or has_tool_messages:
            logger.debug(f"Using tools: {self.tools}")
            params["tools"] = self.tools

        failures = 0
        response = None
        
        # Retry loop for API calls
        while not response:
            try:
                response = self.client.messages.create(**params)
                logger.debug("Got response from Claude API")
                logger.debug(f"Raw response: {response}")
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
        tool_results = []
        references = []
        
        # Variables for processing the streaming response
        current_tool = None
        current_json = ""

        try:
            logger.info("Processing response chunks")
            if stream:
                for chunk in response:
                    logger.debug(f"Raw chunk: {chunk}")
                    
                    if chunk.type == 'content_block_start':
                        if chunk.content_block.type == 'tool_use':
                            # Start of a tool call
                            logger.info(f"Starting tool call with id: {chunk.content_block.id}, name: {chunk.content_block.name}")
                            current_tool = {
                                'id': chunk.content_block.id,
                                'name': chunk.content_block.name,
                                'arguments': ""
                            }
                            logger.debug(f"Starting tool call: {current_tool}")
                            
                    elif chunk.type == 'content_block_delta':
                        if hasattr(chunk.delta, 'text'):
                            text = chunk.delta.text
                            assistant_text += text
                            yield text
                        elif getattr(chunk.delta, 'type', None) == 'citations_delta':
                            # Process citation delta
                            citation = chunk.delta.citation
                            self.citations.append(citation)
                            citation_ref = f" [{len(self.citations)}] "
                            assistant_text += citation_ref
                            yield citation_ref
                        elif hasattr(chunk.delta, 'partial_json'):
                            # Accumulate JSON for tool arguments
                            current_json += chunk.delta.partial_json
                            
                    elif chunk.type == 'content_block_stop':
                        if current_tool:
                            try:
                                arguments = json.loads(current_json)
                                logger.debug(f"Tool arguments: {arguments}")
                                current_tool['args'] = json.dumps(arguments)
                                
                                # Process the tool call right away to get results
                                try:
                                    # Process tool and get results
                                    (tool_result, reference_list) = self.process_tool_call(
                                        current_tool['name'],
                                        current_tool['args'],
                                        current_tool['id']
                                    )
                                    
                                    # Store results for later use when building user message
                                    tool_results.append({
                                        "tool_use_id": current_tool['id'],
                                        "content": "Please see the included reference list below."
                                    })
                                    references.extend(reference_list)
                                    
                                except Exception as e:
                                    logger.error(f"Error processing tool call: {str(e)}")
                                    # Store error for later use
                                    tool_results.append({
                                        "tool_use_id": current_tool['id'],
                                        "content": [{"type": "text", "text": str(e)}]
                                    })
                                
                                # Add to tool calls list
                                tool_calls.append(current_tool)
                                
                                # Reset for next tool
                                current_tool = None
                                current_json = ""
                                
                            except Exception as e:
                                error_msg = f"Tool call failed: {str(e)}"
                                logger.error(error_msg)
                                raise
                            
                    elif chunk.type == 'message_delta':
                        if chunk.delta.stop_reason == 'tool_use':
                            logger.debug("Message stopped for tool use")
                        elif hasattr(chunk.delta, 'text'):
                            text = chunk.delta.text
                            assistant_text += text
                            yield text
                            
                    elif chunk.type == 'message_stop':
                        # Add citations list at the end if there were any citations
                        if self.citations:
                            citations_text = "\n\n**Citations**:\n"
                            logger.debug(f"Full Citations: {self.citations}")
                            for i, citation in enumerate(self.citations, 1):
                                text = getattr(citation, 'cited_text', '')
                                title = getattr(citation, 'document_title', '')
                                citations_text += f"[{i}] {title}:\n {text}\n"
<<<<<<< HEAD
                            assistant_text += citations_text
                            yield citations_text
=======
                            full_response += citations_text
                            yield citations_text 
                            
                        # Add the assistant's message to history
                        if full_response:
                            self.message_history.append({
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": full_response.strip()
                                    }
                                ]
                            })

                        # Process any accumulated tool calls
                        if tool_calls:
                            logger.debug(f"Processing {len(tool_calls)} accumulated tool calls")
                            for tc in tool_calls:
                                try:
                                    # Add tool use to the last assistant message's content
                                    self.message_history[-1]["content"].append({
                                        "type": "tool_use",
                                        "id": tc["id"],
                                        "name": tc["name"],
                                        "input": json.loads(tc["args"])
                                    })
                                    
                                    # Process the tool call
                                    (tool_result, reference_list) = self.process_tool_call(tc["name"], tc["args"], tc["id"])
                                    
                                    logging.info(f"!!!! Reference list:\n{json.dumps(reference_list, indent=2)}")
                                    # Add tool result and reference list in the same message
                                    # Note: Right now, it's unclear what the right thing to do is, 
                                    # if the returned values are intended for RAG. We could include
                                    # both but this increases the token cost for no difference in output. 
                                    self.message_history.append({
                                        "role": "user",
                                        "content": [
                                            {
                                                "type": "tool_result",
                                                "tool_use_id": tc["id"],
                                                # Alternatively, this could be the tool result
                                                "content": "Please see the included reference list below." 
                                            }
                                        ] + reference_list  # Reference list already contains properly formatted documents
                                    })
                                    
                                    if self.message_logger:
                                        self.message_logger.log(self.message_history[-1])  # Tool result
                                    
                                except Exception as e:
                                    logger.error(f"Error processing tool call: {str(e)}")
                                    # Add error as tool result
                                    self.message_history.append({
                                        "role": "user",
                                        "content": [
                                            {
                                                "type": "tool_result",
                                                "tool_use_id": tc["id"],
                                                "content": [{"type": "text", "text": str(e)}]
                                            }
                                        ]
                                    })


                        # Log the assistant message after all tool uses are appended
                        if self.message_logger and full_response:
                            self.message_logger.log(self.message_history[-1])
                        
                        # Reset for next message
                        full_response = ""
                        self.citations = []
                        tool_calls = []
            
>>>>>>> f67369c (Fixed each of the sources.)
            else:
                # Handle non-streaming response
                if response.content:
                    text = response.content[0].text
                    assistant_text += text
                    yield text
                    
                # Extract tool calls from non-streaming response
                for content_block in response.content:
                    if getattr(content_block, 'type', None) == 'tool_use':
                        tool_calls.append({
                            'id': content_block.id,
                            'name': content_block.name,
                            'args': json.dumps(content_block.input)
                        })
                        
                        # Process the tool call
                        try:
                            (tool_result, reference_list) = self.process_tool_call(
                                content_block.name,
                                json.dumps(content_block.input),
                                content_block.id
                            )
                            
                            # Store results for later use
                            tool_results.append({
                                "tool_use_id": content_block.id,
                                "content": "Please see the included reference list below."
                            })
                            references.extend(reference_list)
                            
                        except Exception as e:
                            logger.error(f"Error processing tool call: {str(e)}")
                            tool_results.append({
                                "tool_use_id": content_block.id,
                                "content": [{"type": "text", "text": str(e)}]
                            })
                
            # Now build the complete messages and add them to history
            
            # 1. Build the assistant message with text and any tool calls
            if assistant_text or tool_calls:
                # Start with text content
                content_blocks = []
                if assistant_text:
                    content_blocks.append({
                        "type": "text",
                        "text": assistant_text.strip()
                    })
                
                # Add any tool use blocks
                for tc in tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": json.loads(tc["args"])
                    })
                
                # Create the complete assistant message
                # If assistant text is exactly 1 character long and there are no tool calls,
                # use a simple string instead of a list
                if assistant_text and len(assistant_text.strip()) == 1 and not tool_calls:
                    assistant_message = {
                        "role": "assistant",
                        "content": assistant_text.strip()
                    }
                else:
                    assistant_message = {
                        "role": "assistant",
                        "content": content_blocks
                    }
                
                # Add to history
                self.message_history.append(assistant_message)
                
                # Log the complete message
                if self.message_logger:
                    self._log_message(assistant_message)
            
            # 2. Build the user message with tool results and references if any
            if tool_results:
                # Start with tool result blocks
                content_blocks = []
                for result in tool_results:
                    content_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": result["tool_use_id"],
                        "content": result["content"]
                    })
                
                # Add any reference blocks
                content_blocks.extend(references)
                
                # Create the complete user message
                user_tool_message = {
                    "role": "user",
                    "content": content_blocks
                }
                
                # Add to history
                self.message_history.append(user_tool_message)
                
                # Log the complete message
                if self.message_logger:
                    self._log_message(user_tool_message)
                    
            # Reset for next round
            self.citations = []
                    
        except Exception as e:
            logger.error(f"Error processing response: {str(e)}")
            logger.error(f"Current chunk: {chunk if 'chunk' in locals() else 'No chunk'}")
            raise

    def process_message_history(self, use_tool=True, stream=True):
        logger.debug("!!! Entering process_message_history");
        last_msg = self.message_history[-1]

        # Keep processing the user input until we get something from the assistant
        self.start_time = datetime.now()
        count = 0
        failures = 0
        while self.message_history[-1]["role"] != "assistant":
            try:
                logger.debug("Current message history:\n" + "-" * 60)
                for i, msg in enumerate(self.message_history):
                    logger.debug(f"Message {i}:\n{json.dumps(msg, indent=2)}")
                logger.debug("-" * 60)
                # This is pretty complicated so leaving a comment.
                # We want to yield from so that we can send the sequence through the input
                # Also use tools only if we haven't tried too many times (failure)
                #  and if the last message was not from the tool (success!)
                yield from self.process_one_round(use_tool, stream=stream)
                count += 1
                logger.debug("!!! After iteration")

            except Exception as e:
                failures += 1
                logger.warning(
                    f"Exception occurred in process_message_history: \n{e}\n",
                )
                logger.warning(traceback.format_exc())
                logger.warning("Retrying in 5 seconds...")
                time.sleep(5)
                if failures >= self.settings.MAX_FAILURES:
                    logger.error("Too many failures, aborting")
                    raise Exception("Too many failures") from e
