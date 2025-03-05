# This file aims to define the Ansari class
#   NOTE 1: "Ansari" is basically an LLM equipped with tools (functions) to search the Quran, Hadith, and other sources;
#           Based on the user's query, the LLM determines whether to use a tool or not, and then generates a response.
#   NOTE 2: IMO, a good way to navigate this file is to start from the `replace_message_history` method,
#           as it's main_api.py's entry point to Ansari.
#           I.e., recursively see which methods it calls, and then go to those methods.


import copy
import json
import time
import traceback

import litellm

from ansari.ansari_db import MessageLogger
from ansari.ansari_logger import get_logger
from ansari.config import Settings
from ansari.tools.search_hadith import SearchHadith
from ansari.tools.search_quran import SearchQuran
from ansari.tools.search_tafsir_encyc import SearchTafsirEncyc
from ansari.tools.search_mawsuah import SearchMawsuah
from ansari.util.prompt_mgr import PromptMgr

# previous logger name: __name__ + ".Ansari"
logger = get_logger(__name__)


class Ansari:
    def __init__(self, settings: Settings, message_logger: MessageLogger = None, json_format=False):
        # Base configuration
        self.settings = settings
        self.json_format = json_format
        self.message_logger = message_logger

        # Initialize tools
        self.tool_name_to_instance = self._initialize_tools()
        self.tools = [x.get_tool_description() for x in self.tool_name_to_instance.values()]

        # Initialize prompt manager and system message
        self.pm = PromptMgr(src_dir=settings.PROMPT_PATH)
        self.sys_msg = self.pm.bind(settings.SYSTEM_PROMPT_FILE_NAME).render()

        # Initialize message history with system message
        self.message_history = [{"role": "system", "content": self.sys_msg}]

        self.model = settings.MODEL

    def _initialize_tools(self):
        """Initialize tool instances. Can be overridden by subclasses."""
        sq = SearchQuran(self.settings.KALEMAT_API_KEY.get_secret_value())
        sh = SearchHadith(self.settings.KALEMAT_API_KEY.get_secret_value())
        sm = SearchMawsuah(
            self.settings.VECTARA_API_KEY.get_secret_value(),
            self.settings.MAWSUAH_VECTARA_CORPUS_KEY,
        )
        ste = SearchTafsirEncyc(self.settings.USUL_API_TOKEN.get_secret_value())
        return {
            sq.get_tool_name(): sq,
            sh.get_tool_name(): sh,
            sm.get_tool_name(): sm,
            ste.get_tool_name(): ste,
        }

    def set_message_logger(self, message_logger: MessageLogger):
        self.message_logger = message_logger

    def greet(self):
        self.greeting = self.pm.bind("greeting")
        return self.greeting.render()

    def process_input(self, user_input: str):
        """Process user input and generate a response."""
        logger.debug(f"Processing input: {user_input}")

        # Add user message to history
        self.message_history.append({"role": "user", "content": user_input})
        logger.debug("Added user message to history")

        if self.message_logger:
            self.message_logger.log(role="user", content=user_input)
            logger.debug("Logged user message")

        # Process initial message with tools
        for m in self.process_message_history(use_tool=True):
            if m:
                yield m

        # Ensure we always get a final response (like AnsariClaude)
        if len(self.message_history) > 0 and self.message_history[-1]["role"] != "assistant":
            logger.debug("Last message is not from assistant, making a follow-up call")

            # Search tool will have been used by now, so generate a final response
            for m in self.process_one_round(use_tool=False):
                if m:
                    yield m

    def replace_message_history(self, message_history: list[dict], use_tool=True, stream=True):
        """
        Replaces the current message history (stored in Ansari) with the given message history,
        and then processes it to generate a response from Ansari.
        """
        # Create a new message history, prefix it with Ansari's system message,
        #   then append to it the given message history
        self.message_history = [
            {"role": "system", "content": self.sys_msg},
        ] + message_history

        # Return/Yield Ansari's response to the user
        # TODO(odyash) later (good_first_issue): `stream == False` is not implemented yet; so it has to stay `True`
        for m in self.process_message_history(use_tool, stream=stream):
            if m:
                yield m

    def get_completion(self, **kwargs):
        return litellm.completion(**kwargs)

    def process_message_history(self, use_tool=True, stream=True):
        """
        TODO(odyash) later (good_first_issue): `stream == False` is not implemented yet; so it has to stay `True`
        """
        common_params = {
            "model": self.model,
            "messages": self.message_history,
            "stream": stream,
            "stream_options": {"include_usage": True},
            "timeout": 30.0,
            "temperature": 0.0,
            "metadata": {"generation-name": "ansari"},
            "num_retries": 1,
        }

        failures = 0
        response = None

        while not response:
            try:
                params = {
                    **common_params,
                    **({"tools": self.tools, "tool_choice": "auto"} if use_tool else {}),
                    **({"response_format": {"type": "json_object"}} if self.json_format else {}),
                }
                response = self.get_completion(**params)

            except Exception as e:
                failures += 1
                logger.warning(
                    f"Exception occurred in process_message_history function: \n{e}\n",
                )
                logger.warning(traceback.format_exc())
                logger.warning("Retrying in 5 seconds...")
                time.sleep(5)
                if failures >= self.settings.MAX_FAILURES:
                    logger.error("Too many failures, aborting")
                    raise Exception("Too many failures") from e

        words = ""
        tool_calls = []
        response_mode = ""

        for chunk in response:
            delta = chunk.choices[0].delta

            if delta.content is not None:
                # content chunk
                words += delta.content
                yield delta.content
                response_mode = "words"

            elif delta.tool_calls:
                response_mode = "tool"
                tcchunklist = delta.tool_calls
                for tcchunk in tcchunklist:
                    if len(tool_calls) <= tcchunk.index:
                        tool_calls.append(
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                    tc = tool_calls[tcchunk.index]

                    if tcchunk.id:
                        tc["id"] += tcchunk.id
                    if tcchunk.function.name:
                        tc["function"]["name"] += tcchunk.function.name
                    if tcchunk.function.arguments:
                        tc["function"]["arguments"] += tcchunk.function.arguments

        if response_mode == "words":
            self.message_history.append({"role": "assistant", "content": words})

            # Log the assistant's response to the user's current thread in the DB
            if self.message_logger is not None:
                self.message_logger.log("assistant", words)

        # Run the "function" corresponding to each tool call, and internally store its result(s) in the message history
        # NOTE 1: see `self.tool_name_to_instance` to understand possible "functions" which can get called
        # NOTE 2: even though there's a for loop below,
        #   it's usually just one tool call per user query,
        #   where Ansari determines that this "user query" requires a tool call
        elif response_mode == "tool":
            succ = True
            for tc in tool_calls:
                try:
                    tool_name = tc["function"]["name"]
                    tool_args = tc["function"]["arguments"]
                    tool_id = tc["id"]

                    tool_output_str, internal_msg, tool_msg = self.process_tool_call(tool_name, tool_args, tool_id)

                except json.JSONDecodeError:
                    logger.error(f"Failed to process tool call: {tool_args}")
                    succ = False

            # Log the tool's response to the user's current thread in the DB
            if succ and self.message_logger is not None:
                tool_details = {
                    "internal_message": internal_msg,
                    "tool_message": tool_msg,
                }
                self.message_logger.log("tool", tool_output_str, tool_name, tool_details)

        else:
            raise Exception("Invalid response mode: " + response_mode)

    def process_one_round(self, use_tool=True, stream=True):
        """
        TODO(odyash) later (good_first_issue): `stream == False` is not implemented yet; so it has to stay `True`
        """
        common_params = {
            "model": self.model,
            "messages": self.message_history,
            "stream": stream,
            "stream_options": {"include_usage": True},
            "timeout": 30.0,
            "temperature": 0.0,
            "metadata": {"generation-name": "ansari"},
            "num_retries": 1,
        }

        failures = 0
        response = None

        while not response:
            try:
                params = {
                    **common_params,
                    **({"tools": self.tools, "tool_choice": "auto"} if use_tool else {}),
                    **({"response_format": {"type": "json_object"}} if self.json_format else {}),
                }
                response = self.get_completion(**params)

            except Exception as e:
                failures += 1
                logger.warning(
                    f"Exception occurred in process_one_round function: \n{e}\n",
                )
                logger.warning(traceback.format_exc())
                logger.warning("Retrying in 5 seconds...")
                time.sleep(5)
                if failures >= self.settings.MAX_FAILURES:
                    logger.error("Too many failures, aborting")
                    raise Exception("Too many failures") from e

        words = ""
        tool_calls = []
        response_mode = ""

        for chunk in response:
            delta = chunk.choices[0].delta

            if delta.content is not None:
                # content chunk
                words += delta.content
                yield delta.content
                response_mode = "words"

            elif delta.tool_calls:
                response_mode = "tool"
                tcchunklist = delta.tool_calls
                for tcchunk in tcchunklist:
                    if len(tool_calls) <= tcchunk.index:
                        tool_calls.append(
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                    tc = tool_calls[tcchunk.index]

                    if tcchunk.id:
                        tc["id"] += tcchunk.id
                    if tcchunk.function.name:
                        tc["function"]["name"] += tcchunk.function.name
                    if tcchunk.function.arguments:
                        tc["function"]["arguments"] += tcchunk.function.arguments

        if response_mode == "words":
            self.message_history.append({"role": "assistant", "content": words})

            # Log the assistant's response to the user's current thread in the DB
            if self.message_logger is not None:
                self.message_logger.log("assistant", words)

        # Run the "function" corresponding to each tool call, and internally store its result(s) in the message history
        # NOTE 1: see `self.tool_name_to_instance` to understand possible "functions" which can get called
        # NOTE 2: even though there's a for loop below,
        #   it's usually just one tool call per user query,
        #   where Ansari determines that this "user query" requires a tool call
        elif response_mode == "tool":
            succ = True
            for tc in tool_calls:
                try:
                    tool_name = tc["function"]["name"]
                    tool_args = tc["function"]["arguments"]
                    tool_id = tc["id"]

                    tool_output_str, internal_msg, tool_msg = self.process_tool_call(tool_name, tool_args, tool_id)

                except json.JSONDecodeError:
                    logger.error(f"Failed to process tool call: {tool_args}")
                    succ = False

            # Log the tool's response to the user's current thread in the DB
            if succ and self.message_logger is not None:
                tool_details = {
                    "internal_message": internal_msg,
                    "tool_message": tool_msg,
                }
                self.message_logger.log("tool", tool_output_str, tool_name, tool_details)

        else:
            raise Exception("Invalid response mode: " + response_mode)

    def process_tool_call(
        self,
        tool_name: str,
        tool_args: str,
        tool_id: str,
    ):
        if tool_name not in self.tool_name_to_instance.keys():
            logger.warning(f"Unknown tool name: {tool_name}")
            return
        try:
            logger.debug(f"Tool args: {tool_args}")
            args_dict = json.loads(tool_args)
            logger.debug(f"Parsed tool args: {args_dict}")
            query: str = args_dict["query"]
            logger.debug(f"Extracted query: {query}")
        except json.JSONDecodeError:
            logger.error(f"JSON decode error for tool args: {tool_args}")
            raise json.JSONDecodeError
        except KeyError as e:
            logger.error(f"Missing key in tool args: {e} - Tool args: {tool_args}")
            query = ""

        tool_instance = self.tool_name_to_instance[tool_name]
        logger.debug(f"Running {tool_name} with query: {query}")
        try:
            # Get raw results directly using run() instead of run_as_list()
            raw_results = tool_instance.run(query)
            logger.debug(f"Raw results type: {type(raw_results)}")

            # Format the results as a list of strings
            results = tool_instance.format_as_list(raw_results)
            logger.debug(f"Formatted results type: {type(results)}")
            logger.debug(f"Results sample: {str(results)[:200] if results else 'Empty results'}")
        except Exception as e:
            import traceback

            logger.error(f"Error running {tool_name}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Return an error message as results
            results = [f"Error running {tool_name}: {str(e)}"]

        tool_definition = {
            "name": tool_name,
            "arguments": tool_args,
        }

        # we have to first add this message before any tool response, as mentioned in this source:
        # https://platform.openai.com/docs/guides/function-calling#submitting-function-output
        internal_msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"type": "function", "id": tool_id, "function": tool_definition},
            ],
        }
        self.message_history.append(internal_msg)

        # Log the assistant's tool call message
        if self.message_logger is not None:
            self.message_logger.log(
                "assistant", "", tool_name, {"function": tool_definition, "id": tool_id, "type": "function"}
            )

        if len(results) == 0:
            # corner case where the api returns no results
            msg_prefix = "No results found"
        else:
            # instruct the model to paraphrase the tool's output
            logger.debug(f"#num of returned results from external API: {len(results)}")
            msg_prefix = (
                ""
                # "Integrate the following most relevant citations in your final response:\n"
            )

        # Now we have to pass the results back in
        # NOTE: "citation" == ayah/hadith/etc. (based on the called tool)
        try:
            # Ensure results is a list of strings
            if not isinstance(results, list):
                logger.error(f"Results is not a list: {type(results)}")
                results = [str(results)]
            elif not all(isinstance(item, str) for item in results):
                logger.warning("Not all results are strings, converting to strings")
                results = [str(item) for item in results]

            results_str = msg_prefix + "\nAnother relevant citation:\n".join(results)
        except Exception as e:
            logger.error(f"Error joining results: {str(e)}")
            logger.error(f"Results that caused error: {results}")
            results_str = f"Error processing results: {str(e)}"

        msg_generated_from_tool = {
            "role": "tool",
            "content": results_str,
            "tool_call_id": tool_id,
        }
        self.message_history.append(msg_generated_from_tool)

        return msg_generated_from_tool["content"], internal_msg, msg_generated_from_tool

    def _log_truncated_message_history(self, message_history, count: int, failures: int):
        """
        Logs a truncated version of the message history for debugging purposes.

        Args:
            message_history (list): The message history to be truncated and logged.
        """
        trunc_msg_hist = copy.deepcopy(message_history)
        if (
            len(trunc_msg_hist) > 1
            and isinstance(trunc_msg_hist[0], dict)
            and "role" in trunc_msg_hist[0]
            and trunc_msg_hist[0]["role"] == "system"
            and "content" in trunc_msg_hist[0]
        ):
            sys_p = trunc_msg_hist[0]["content"]
            trunc_msg_hist[0]["content"] = sys_p[:15] + "..."

        logger.info(
            f"Process attempt #{count + failures + 1} of this message history:\n"
            + "-" * 60
            + f"\n{trunc_msg_hist}\n"
            + "-" * 60,
        )
