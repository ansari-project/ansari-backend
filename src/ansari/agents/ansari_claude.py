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

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
        results = tool_instance.run_as_list(query)
        
        if len(results) == 0:
            return ["No results found"]
            
        logger.info(f"Got {len(results)} results from API")
        return results

    def process_one_round(self, use_tool=True, stream=True) -> Generator[str, None, None]:
        """Process one round of conversation.
        
        Args:
            use_tool: Whether to allow tool usage. Intended to be used when using a tool fails. 
            stream: Whether to stream the response
            
        Yields:
            Chunks of the response text

        Side effect: 
            - Updates the message history
            - Logs updates to the message history. 
        """
        prompt_mgr = PromptMgr()
        system_prompt = prompt_mgr.bind("system_msg_claude").render()

        logger.debug(f"Sending messages to Claude: {self.message_history}")
        
        # Create API request parameters
        params = {
            "model": "claude-3-5-sonnet-20241022",
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
                logger.info("Got response from Claude API")
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

        # Process the response
        full_response = ""
        tool_calls = []
        current_tool = None
        current_json = ""
        citations = []
        citation_texts = []

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
                            full_response += text
                            yield text
                        elif getattr(chunk.delta, 'type', None) == 'citations_delta':
                            # Process citation delta
                            citation = chunk.delta.citation
                            self.citations.append(citation)
                            citation_ref = f" [{len(self.citations)}] "
                            full_response += citation_ref
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
                                tool_calls.append(current_tool)
                                
                                # Reset for next tool
                                current_tool = None
                                current_json = ""
                                
                            except Exception as e:
                                error_msg = f"Tool call failed: {str(e)}"
                                logger.error(error_msg)
                                tool_calls.append({
                                    "tool": current_tool,
                                    "error": error_msg,
                                    "traceback": traceback.format_exc()
                                })
                                raise
                            
                    elif chunk.type == 'message_delta':
                        if chunk.delta.stop_reason == 'tool_use':
                            logger.debug("Message stopped for tool use")
                        elif hasattr(chunk.delta, 'text'):
                            text = chunk.delta.text
                            full_response += text
                            yield text
                            
                    elif chunk.type == 'message_stop':
                        # Add citations list at the end if there were any citations
                        if self.citations:
                            citations_text = "\n\n**Citations**:\n"
                            for i, citation in enumerate(self.citations, 1):
                                text = getattr(citation, 'cited_text', '')
                                citations_text += f"[{i}] {text}\n"
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
                                    result = self.process_tool_call(tc["name"], tc["args"], tc["id"])
                                    
                                    # Add tool result as user message
                                    self.message_history.append({
                                        "role": "user",
                                        "content": [
                                            {
                                                "type": "tool_result",
                                                "tool_use_id": tc["id"],
                                                "content": [{"type": "text", "text": r} for r in (result if isinstance(result, list) else [result])]
                                            }
                                        ] + [
                                            {
                                                "type": "document",
                                                "source": {
                                                    "type": "text",
                                                    "media_type": "text/plain",
                                                    "data": r
                                                },
                                                "title": f"Tool Result {i+1}: {tc['name']}",
                                                "context": f"Result from tool call {tc['id']}",
                                                "citations": {"enabled": True}
                                            } for i, r in enumerate(result if isinstance(result, list) else [result])
                                        ]
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
            
            else:
                # Handle non-streaming response
                if response.content:
                    text = response.content[0].text
                    full_response += text
                    yield text
            
            # Add response to message history
            if full_response:
                logger.debug(f"Adding text response to history: {full_response}")
                self.message_history.append({
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": full_response.strip()
                        }
                    ]
                })
                if self.message_logger:
                    self.message_logger.log(self.message_history[-1])
                    
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
            logger.debug("!!! Process message loop")
            try:
                logger.info("Current message history:\n" + "-" * 60)
                for i, msg in enumerate(self.message_history):
                    logger.info(f"Message {i}:\n{json.dumps(msg, indent=2)}")
                logger.info("-" * 60)
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

        logger.debug("!!! Exiting process_message_history");
        logger.debug(f"Final message history:\n" + "-" * 60)
        for i, msg in enumerate(self.message_history):
            logger.debug(f"Message {i}:\n{json.dumps(msg, indent=2)}")
        logger.debug("-" * 60)
