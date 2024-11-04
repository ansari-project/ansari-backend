import hashlib
import json
import logging
import os
import re
import sys
import time
import traceback
from datetime import date, datetime
from typing import Union

import litellm
from langfuse.decorators import langfuse_context, observe

from tools.search_hadith import SearchHadith
from tools.search_mawsuah import SearchMawsuah
from tools.search_quran import SearchQuran
from util.prompt_mgr import PromptMgr

logger = logging.getLogger(__name__ + ".Ansari")

if not sys.argv[0].endswith("main_api.py"):
    logging_mode = logging.DEBUG
else:
    logging_mode = logging.INFO

logger.setLevel(logging_mode)

# # Uncomment below when logging above doesn't output to std, and you want to see the logs in the console
# console_handler = logging.StreamHandler()
# console_handler.setLevel(logging_mode)
# logger.addHandler(console_handler)


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
        self.tool_name_to_instance = {
            sq.get_tool_name(): sq,
            sh.get_tool_name(): sh,
            sm.get_tool_name(): sm,
        }
        self.model = settings.MODEL
        self.pm = PromptMgr()
        self.sys_msg = self.pm.bind(settings.SYSTEM_PROMPT_FILE_NAME).render()
        self.tools = [
            x.get_tool_description() for x in self.tool_name_to_instance.values()
        ]
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

    def process_input(self, user_input, use_tool=True, stream=True):
        self.message_history.append({"role": "user", "content": user_input})
        return self.process_message_history(use_tool, stream=stream)

    def log(self):
        if not os.environ.get("LANGFUSE_SECRET_KEY"):
            return
        trace_id = self.compute_trace_id()
        logger.info(f"trace id is {trace_id}")
    
    def _execute_search_step(self, step_params, prev_outputs):
        tool = self.tool_name_to_instance[step_params["tool_name"]]
        print(tool)
        print(step_params)
        print(prev_outputs)
        print(prev_outputs[step_params["query_from_prev_output_index"]])
        if "query" in step_params:
            results = tool.run_as_string(step_params["query"])
        elif "query_from_prev_output_index" in step_params:
            results = tool.run_as_string(prev_outputs[step_params["query_from_prev_output_index"]])
        else:
            raise ValueError("search step must have either query or query_from_prev_output_index")
        return results

    def _execute_gen_query_step(self, step_params, prev_outputs):
        prompt = f"""Generate 3-5 key terms or phrases for searching the input: '{step_params["input"]}' in the '{step_params["target_corpus"]}' corpus. These search terms should be:

        - Relevant words/phrases that appear in or closely match content in '{step_params["target_corpus"]}'
        - Usable for both keyword and semantic search
        - Given as a simple list without explanation or complete sentences"""
        model_response = litellm.completion(
                model=self.model,
                messages=[{"role": "system", "content": self.sys_msg}, {"role": "user", "content": prompt}],
                stream=False,
                timeout=30.0,
                temperature=0.0,
                metadata={"generation-name": "gen-query"},
                num_retries=1,
                response_format=None,
                functions=None,
            )
        return model_response.choices[0].message.content


    def _execute_gen_answer_step(self, step_params, prev_outputs):
        if step_params.get("search_results_indices"):
            search_results = "\n---\n".join([prev_outputs[i] for i in step_params["search_results_indices"]])
        prompt = f"""Using {search_results}, compose a response that:
            1. Answers the query
            2. Matches user's language/tone
            3. Adheres to your system instructions as Ansari."""
        self.message_history.append(
                        {"role": "system", "content": prompt}
                    )
        return self.process_input(step_params["input"], use_tool=False, stream=False)

    def execute_workflow(self, workflow_steps: list[tuple[str, dict]]):
        # this function handles v3 logic
        # the idea is to have Ansari execute a workflow
        # that can be a list of steps
        # allowed steps are:
        # a. search in a corpus
        # b. generate query
        # c. generate answer
        outputs = []
        step_name_to_fn = {"search": self._execute_search_step, "gen_query": self._execute_gen_query_step, "gen_answer": self._execute_gen_answer_step}
        for step_name, step_params in workflow_steps:
            outputs.append(step_name_to_fn[step_name](step_params, outputs))
        return outputs

    @observe()
    def replace_message_history(self, message_history, use_tool=True, stream=True):
        self.message_history = [
            {"role": "system", "content": self.sys_msg}
        ] + message_history
        print(f"Original trace is {self.message_logger.trace_id}")
        print(f"Id 1 is {langfuse_context.get_current_trace_id()}")
        # langfuse_context._set_root_trace_id(self.message_logger.trace_id)
        print(f"Id 2 is {langfuse_context.get_current_trace_id()}")
        langfuse_context.update_current_observation(
            user_id=self.message_logger.user_id,
            session_id=str(self.message_logger.thread_id),
            tags=["debug", "replace_message_history"],
        )
        for m in self.process_message_history(use_tool, stream=stream):
            if m:
                yield m

    @observe(capture_input=False, capture_output=False)
    def process_message_history(self, use_tool=True, stream=True):
        if self.message_logger is not None:
            langfuse_context.update_current_trace(
                user_id=self.message_logger.user_id,
                session_id=str(self.message_logger.thread_id),
                tags=["debug", "replace_message_history"],
                input=self.message_history,
            )
        # Keep processing the user input until we get something from the assistant
        self.start_time = datetime.now()
        count = 0
        failures = 0
        while (
            self.message_history[-1]["role"] != "assistant"
            or "tool_call_id" in self.message_history[-1]
        ):
            try:
                logger.info(
                    f"Process attempt #{count+failures+1} of this message history:\n"
                    + "-" * 60
                    + f"\n{self.message_history}\n"
                    + "-" * 60
                )
                # This is pretty complicated so leaving a comment.
                # We want to yield from so that we can send the sequence through the input
                # Also use tools only if we haven't tried too many times  (failure) and if the last message was not from the tool (success!)
                use_tool = use_tool and (
                    count < self.settings.MAX_TOOL_TRIES
                ) and self.message_history[-1]["role"] != "tool"
                if not use_tool:
                    status_msg = (
                        "Not using tools -- tries exceeded"
                        if count >= self.settings.MAX_TOOL_TRIES
                        else 'Used tools! will paraphrase using "words" mode ...'
                    )
                    logger.warning(status_msg)
                yield from self.process_one_round(use_tool, stream=stream)
                count += 1
            except Exception as e:
                failures += 1
                logger.warning(
                    f"Exception occurred in process_message_history: \n{e}\n"
                )
                logger.warning(traceback.format_exc())
                logger.warning("Retrying in 5 seconds...")
                time.sleep(5)
                if failures >= self.settings.MAX_FAILURES:
                    logger.error("Too many failures, aborting")
                    raise Exception("Too many failures")
                    break
        self.log()

    def get_completion(self, **kwargs):
        return litellm.completion(**kwargs)

    @staticmethod
    def _extract_unique_json_objects(json_string: str) -> list[dict[str, str]]:
        """
        Extract unique JSON objects from a string and return them as a list of JSON strings.

        This function takes a string containing multiple JSON objects and extracts unique JSON objects,
        returning them as a list of JSON strings.

        Args:
            json_string (str): A string containing multiple JSON objects.

        Returns:
            list: A list of unique JSON strings.

        Example:
            >>> json_string = '{"query": "2:1"}{"query": "2:2"}{"query": "2:1"}'
            >>> unique_json_list = _extract_unique_json_objects(json_string)
            >>> print(unique_json_list)
            ['{"query": "2:1"}', '{"query": "2:2"}']
        """
        # Use regular expression to find all unique JSON objects in the string
        json_strs = list(set(re.findall(r"\{.*?\}", json_string)))

        # Convert to list of python dictionaries
        json_objects = [json.loads(s) for s in json_strs]

        return json_objects

    @observe(as_type="generation")
    def process_one_round(self, use_tool=True, stream=True):
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
                    **({"response_format": {"type": "json_object"}} if self.json_format else {})
                }
                response = self.get_completion(**params)

            except Exception as e:
                failures += 1
                logger.warning(
                    f"Exception occurred in process_one_round function: \n{e}\n"
                )
                logger.warning(traceback.format_exc())
                logger.warning("Retrying in 5 seconds...")
                time.sleep(5)
                if failures >= self.settings.MAX_FAILURES:
                    logger.error("Too many failures, aborting")
                    raise Exception("Too many failures")

        words = ""
        # "tool" is synonymous with "function", as that's currently the only
        # supported type by the model provider (e.g., OpenAI)
        tool_name = ""
        tool_arguments = ""
        tool_id = ""
        response_mode = ""  # words or tool

        # side note: the `response` should be litellm.utils.CustomStreamWrapper object
        for tok in response:
            if len(tok.choices) == 0:  # in case usage is defind.q
                logging.warning(f"Token has no choices: {tok}")
                langfuse_context.update_current_observation(usage=tok.usage)
            delta = tok.choices[0].delta
            if not response_mode:
                # This code should only trigger the first
                # time through the loop.
                logger.debug(
                    f"\n\nFirst tok is {tok}\n\n"
                )  # uncomment when debugging only
                if "tool_calls" in delta and delta.tool_calls:
                    # We are in tool mode
                    response_mode = "tool"
                    tool_name = delta.tool_calls[0].function.name
                    tool_id = delta.tool_calls[0].id
                else:
                    response_mode = "words"
                logger.info("Response mode: " + response_mode)

            # We process things differently depending on whether it is a tool or a
            # text
            if response_mode == "words":
                # there are still tokens to be processed
                if delta.content is not None:
                    words += delta.content
                    yield delta.content
                # End token
                elif delta.content is None:
                    self.message_history.append({"role": "assistant", "content": words})
                    langfuse_context.update_current_observation(
                        output=words, metadata={"delta": delta}
                    )
                    if self.message_logger:
                        self.message_logger.log("assistant", words)
                    break
                else:
                    continue
            elif response_mode == "tool":
                logger.debug(f"Delta in: {delta}")
                # shouldn't occur unless model provider's/LiteLLM's API is changed
                if "tool_calls" not in delta:
                    logger.warning(f"Weird delta: {delta}")
                    continue
                # There are still tokens to be processed
                if delta.tool_calls:
                    # logger.debug(f"delta.tool_calls is {delta.tool_calls}")
                    args_str = delta.tool_calls[0].function.arguments
                    tool_arguments += args_str
                # End token
                else:
                    # this returned list could have > 1 element if the
                    # AI model deduced that the user queried for > 1 topic in the same prompt
                    tool_arguments: list[dict[str, str]] = (
                        self._extract_unique_json_objects(tool_arguments)
                    )

                    # "process_tool_call" will append the tool call(s) to the message history
                    for cur_args in tool_arguments:
                        self.process_tool_call(
                            tool_name,
                            cur_args,
                            tool_id,
                            tool_definition={
                                "name": tool_name,
                                # can be "arguments": "{}" as well
                                "arguments": str(cur_args),
                            },
                        )
                    break
            else:
                raise Exception("Invalid response mode: " + response_mode)

    @observe()
    def process_tool_call(
        self,
        tool_name: str,
        tool_arguments: dict[str],
        tool_id: str,
        tool_definition: dict[str, str],
    ):
        if tool_name not in self.tool_name_to_instance.keys():
            logger.warning(f"Unknown tool name: {tool_name}")
            return

        logger.debug(f"tool_arguments are\n{tool_arguments}\n")
        query: str = tool_arguments["query"]
        tool_instance: Union[SearchQuran, SearchHadith] = self.tool_name_to_instance[
            tool_name
        ]
        results = tool_instance.run_as_list(query)
        # print(f"Results are {results}")

        # we have to first add this message before any tool response, as mentioned in this source:
        # https://platform.openai.com/docs/guides/function-calling/step-5-provide-the-function-call-result-back-to-the-model
        self.message_history.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"type": "function", "id": tool_id, "function": tool_definition}
                ],
            }
        )

        if len(results) == 0:
            # corner case where the api returns no results
            msg_prefix = "No results found"
        else:
            # instruct the model to paraphrase the tool's output
            logger.debug(f"#num of returned results from external API: {len(results)}")
            msg_prefix = (
                ""
                # "Integrate the following most relevant ayahs in your final response:\n"
            )

        # Now we have to pass the results back in
        results_str = msg_prefix + "\nAnother relevant ayah:\n".join(results)
        self.message_history.append(
            {"role": "tool", "content": results_str, "tool_call_id": tool_id}
        )
