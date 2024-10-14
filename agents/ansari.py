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
        self.tools = {sq.get_fn_name(): sq, sh.get_fn_name(): sh, sm.get_fn_name(): sm}
        self.model = settings.MODEL
        self.pm = PromptMgr()
        self.sys_msg = self.pm.bind(settings.SYSTEM_PROMPT_FILE_NAME).render()
        self.functions = [x.get_function_description() for x in self.tools.values()]
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
                logger.info(f"Processing one round {self.message_history}")
                # This is pretty complicated so leaving a comment.
                # We want to yield from so that we can send the sequence through the input
                # Also use functions only if we haven't tried too many times
                use_function = True
                if count >= self.settings.MAX_FUNCTION_TRIES:
                    use_function = False
                    logger.warning("Not using functions -- tries exceeded")
                yield from self.process_one_round(use_function)
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
    def process_one_round(self, use_function=True):
        response = None
        failures = 0
        while not response:
            try:
                if use_function:
                    if self.json_format:
                        response = litellm.completion(
                            model=self.model,
                            messages=self.message_history,
                            stream=True,
                            stream_options = {"include_usage": True}, 
                            functions=self.functions,
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
                            functions=self.functions,
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
        function_name = ""
        function_arguments = ""
        response_mode = ""  # words or fn
        for tok in response:
            if len(tok.choices) == 0: # in case usage is defind.q 
                logging.warning(f"Token has no choices: {tok}")
                langfuse_context.update_current_observation(usage = tok.usage)  
            delta = tok.choices[0].delta
            if not response_mode:
                # This code should only trigger the first
                # time through the loop.
                if "function_call" in delta and delta.function_call:
                    # We are in function mode
                    response_mode = "fn"
                    function_name = delta.function_call.name
                else:
                    response_mode = "words"
                logger.info("Response mode: " + response_mode)

            # We process things differently depending on whether it is a function or a
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
            elif response_mode == "fn":
                logger.debug("Delta in: ", delta)
                if (
                    "function_call" not in delta or delta["function_call"] is None
                ):  # End token
                    _ = function_name + "(" + function_arguments + ")"
                    # The function call below appends the function call to the message history
                    print(f"{function_name=}, {function_arguments=}")
                    yield self.process_fn_call(input, function_name, function_arguments)
                    #
                    break
                elif (
                    "function_call" in delta
                    and delta.function_call
                    and delta.function_call.arguments
                ):
                    function_arguments += delta.function_call.arguments
                    logger.debug(f"Function arguments are {function_arguments}")
                    yield ""  # delta['function_call']['arguments'] # we shouldn't yield anything if it's a fn
                else:
                    logger.warning(f"Weird delta: {delta}")
                    continue
            else:
                raise Exception("Invalid response mode: " + response_mode)

    @observe()
    def process_fn_call(self, orig_question, function_name, function_arguments):
        if function_name in self.tools.keys():
            args = json.loads(function_arguments)
            query = args["query"]
            results = self.tools[function_name].run_as_list(query)
            logger.debug(f"Results are {results}")
            # Now we have to pass the results back in
            if len(results) > 0:
                for result in results:
                    self.message_history.append(
                        {"role": "function", "name": function_name, "content": result}
                    )
                    if self.message_logger:
                        self.message_logger.log("function", result, function_name)
            else:
                self.message_history.append(
                    {
                        "role": "function",
                        "name": function_name,
                        "content": "No results found",
                    }
                )
                if self.message_logger:
                    self.message_logger.log(
                        "function", "No results found", function_name
                    )
        else:
            logger.warning(f"Unknown function name: {function_name}")
