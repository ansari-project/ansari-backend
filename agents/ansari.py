import hashlib
import json
import logging
import os
import time
import traceback
from datetime import date, datetime

import litellm

from tools.search_hadith import SearchHadith
from tools.search_mawsuah import SearchMawsuah
from tools.search_quran import SearchQuran
from util.prompt_mgr import PromptMgr
from langfuse.decorators import observe, langfuse_context

logger = logging.getLogger(__name__ + ".Ansari")
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)


class Ansari:
    def __init__(self, settings, message_logger=None, json_format=False):
        self.settings = settings
        sq = SearchQuran(settings.KALEMAT_API_KEY.get_secret_value())
        sh = SearchHadith(settings.KALEMAT_API_KEY.get_secret_value())
        sm = SearchMawsuah(
            settings.VECTARA_AUTH_TOKEN.get_secret_value(),
            settings.VECTARA_CUSTOMER_ID,
            settings.VECTARA_CORPUS_ID,
        )
        self.tools = {sq.get_tool_name(): sq, sh.get_tool_name(): sh, sm.get_tool_name(): sm}
        self.model = settings.MODEL
        self.pm = PromptMgr()
        self.sys_msg = self.pm.bind(settings.SYSTEM_PROMPT_FILE_NAME).render()
        self.tools = [x.get_tool_description() for x in self.tools.values()]
        self.message_history = [{"role": "system", "content": self.sys_msg}]
        self.json_format = json_format
        self.message_logger = message_logger

    def set_message_logger(self, message_logger):
        self.message_logger = message_logger

    # The trace id is a hash of the first user input and the time.
    def compute_trace_id(self):
        today = date.today()
        hashstring = str(today) + self.message_history[1]["content"]
        result = hashlib.md5(hashstring.encode())
        return "chash_" + result.hexdigest()

    def greet(self):
        self.greeting = self.pm.bind("greeting")
        return self.greeting.render()

    def process_input(self, user_input):
        self.message_history.append({"role": "user", "content": user_input})
        return self.process_message_history()

    def log(self):
        if not os.environ.get("LANGFUSE_SECRET_KEY"):
            return
        trace_id = self.compute_trace_id()
        logger.info(f"trace id is {trace_id}")
  
    @observe()
    def replace_message_history(self, message_history ):
        self.message_history = [
            {"role": "system", "content": self.sys_msg}
        ] + message_history
        print(f'Original trace is {self.message_logger.trace_id}');
        print(f'Id 1 is {langfuse_context.get_current_trace_id()}');
        #langfuse_context._set_root_trace_id(self.message_logger.trace_id)
        print(f'Id 2 is {langfuse_context.get_current_trace_id()}');
        langfuse_context.update_current_observation (
            user_id = self.message_logger.user_id,
            session_id = str(self.message_logger.thread_id),
            tags = ['debug', 'replace_message_history']
        )
        for m in self.process_message_history():
            if m:
                yield m
    

    @observe(capture_input = False,capture_output = False)
    def process_message_history(self):
        if self.message_logger is not None:
            langfuse_context.update_current_trace(
                user_id = self.message_logger.user_id,
                session_id = str(self.message_logger.thread_id),
                tags = ['debug', 'replace_message_history'],
                input = self.message_history
            )
        # Keep processing the user input until we get something from the assistant
        self.start_time = datetime.now()
        count = 0
        failures = 0
        while self.message_history[-1]["role"] != "assistant":
            try:
                logger.info(f"Process attempt #{count+failures+1} of this message history: {self.message_history}")
                # This is pretty complicated so leaving a comment.
                # We want to yield from so that we can send the sequence through the input
                # Also use tools only if we haven't tried too many times
                use_tool = True
                if count >= self.settings.MAX_TOOL_TRIES:
                    use_tool = False
                    logger.warning("Not using tools -- tries exceeded")
                yield from self.process_one_round(use_tool)
                count += 1
            except Exception:
                failures += 1
                logger.warning("Exception occurred: {e}")
                logger.warning(traceback.format_exc())
                logger.warning("Retrying in 5 seconds...")
                time.sleep(5)
                if failures >= self.settings.MAX_FAILURES:
                    logger.error("Too many failures, aborting")
                    raise Exception("Too many failures")
                    break
        self.log()

    @observe(as_type="generator")
    def process_one_round(self, use_tool=True):
        response = None
        failures = 0
        while not response:
            try:
                if use_tool:
                    if self.json_format:
                        response = litellm.completion(
                            model=self.model,
                            messages=self.message_history,
                            stream=True,
                            stream_options = {"include_usage": True}, 
                            tools=self.tools,
                            timeout=30.0,
                            temperature=0.0,
                            metadata={"generation-name": "ansari"},
                            response_format={"type": "json_object"},
                            num_retries=1,
                        )
                    else:
                        response = litellm.completion(
                            model=self.model,
                            messages=self.message_history,
                            stream=True,
                            stream_options = {"include_usage": True}, 
                            tools=self.tools,
                            timeout=30.0,
                            temperature=0.0,
                            metadata={"generation-name": "ansari"},
                            num_retries=1,
                        )
                else:
                    if self.json_format:
                        response = litellm.completion(
                            model=self.model,
                            messages=self.message_history,
                            stream=True,
                            stream_options = {"include_usage": True}, 
                            timeout=30.0,
                            temperature=0.0,
                            response_format={"type": "json_object"},
                            metadata={"generation-name": "ansari"},
                            num_retries=1,
                        )
                    else:
                        response = litellm.completion(
                            model=self.model,
                            messages=self.message_history,
                            stream=True,
                            stream_options = {"include_usage": True}, 
                            timeout=30.0,
                            temperature=0.0,
                            metadata={"generation-name": "ansari"},
                            num_retries=1,
                        )

            except Exception as e:
                failures += 1
                logger.warning("Exception occurred: ", e)
                logger.warning(traceback.format_exc())
                logger.warning("Retrying in 5 seconds...")
                time.sleep(5)
                if failures >= self.settings.MAX_FAILURES:
                    logger.error("Too many failures, aborting")
                    raise Exception("Too many failures")
                    break

        words = ""
        tool_name = ""
        tool_arguments = ""
        response_mode = ""  # words or tool
        for tok in response:
            if len(tok.choices) == 0: # in case usage is defind.q 
                logging.warning(f"Token has no choices: {tok}")
                langfuse_context.update_current_observation(usage = tok.usage)  
            delta = tok.choices[0].delta
            if not response_mode:
                # This code should only trigger the first
                # time through the loop.
                if "tool_call" in delta and delta.tool_call:
                    # We are in tool mode
                    response_mode = "tool"
                    tool_name = delta.tool_call.name
                else:
                    response_mode = "words"
                logger.info("Response mode: " + response_mode)

            # We process things differently depending on whether it is a tool or a
            # text
            if response_mode == "words":
                if delta.content is None:  # End token
                    self.message_history.append({"role": "assistant", "content": words})
                    langfuse_context.update_current_observation(
                        output = words, 
                        metadata = {"delta": delta}
                    )
                    if self.message_logger:
                        self.message_logger.log("assistant", words)
                    break
                elif delta.content is not None:
                    words += delta.content
                    yield delta.content
                else:
                    continue
            elif response_mode == "tool":
                logger.debug("Delta in: ", delta)
                if (
                    "tool_call" not in delta or delta["tool_call"] is None
                ):  # End token
                    _ = tool_name + "(" + tool_arguments + ")"
                    # The tool call below appends the tool call to the message history
                    print(f"{tool_name=}, {tool_arguments=}")
                    yield self.process_tool_call(input, tool_name, tool_arguments)
                    #
                    break
                elif (
                    "tool_call" in delta
                    and delta.tool_call
                    and delta.tool_call.arguments
                ):
                    tool_arguments += delta.tool_call.arguments
                    logger.debug(f"tool arguments are {tool_arguments}")
                    yield ""  # delta['tool_call']['arguments'] # we shouldn't yield anything if it's a tool
                else:
                    logger.warning(f"Weird delta: {delta}")
                    continue
            else:
                raise Exception("Invalid response mode: " + response_mode)

    @observe()
    def process_tool_call(self, orig_question, tool_name, tool_arguments):
        if tool_name in self.tools.keys():
            args = json.loads(tool_arguments)
            query = args["query"]
            results = self.tools[tool_name].run_as_list(query)
            logger.debug(f"Results are {results}")
            # Now we have to pass the results back in
            if len(results) > 0:
                for result in results:
                    self.message_history.append(
                        {"role": "tool", "name": tool_name, "content": result}
                    )
                    if self.message_logger:
                        self.message_logger.log("tool", result, tool_name)
            else:
                self.message_history.append(
                    {
                        "role": "tool",
                        "name": tool_name,
                        "content": "No results found",
                    }
                )
                if self.message_logger:
                    self.message_logger.log(
                        "tool", "No results found", tool_name
                    )
        else:
            logger.warning(f"Unknown tool name: {tool_name}")
