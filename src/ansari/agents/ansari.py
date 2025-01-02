import hashlib
import json
import os
import time
import traceback
from datetime import date, datetime

import litellm
from langfuse.decorators import langfuse_context, observe

from ansari.ansari_db import MessageLogger
from ansari.ansari_logger import get_logger
from ansari.tools.search_hadith import SearchHadith
from ansari.tools.search_quran import SearchQuran
from ansari.tools.search_vectara import SearchVectara
from ansari.util.prompt_mgr import PromptMgr

# previous logger name: __name__ + ".Ansari"
logger = get_logger()


class Ansari:
    def __init__(self, settings, message_logger: MessageLogger = None, json_format=False):
        self.settings = settings
        self.json_format = json_format
        self.message_logger = message_logger
        sq = SearchQuran(settings.KALEMAT_API_KEY.get_secret_value())
        sh = SearchHadith(settings.KALEMAT_API_KEY.get_secret_value())
        sm = SearchVectara(
            settings.VECTARA_API_KEY.get_secret_value(),
            settings.MAWSUAH_VECTARA_CORPUS_KEY,
            settings.MAWSUAH_FN_NAME,
            settings.MAWSUAH_FN_DESCRIPTION,
            settings.MAWSUAH_TOOL_PARAMS,
            settings.MAWSUAH_TOOL_REQUIRED_PARAMS,
        )
        self.tool_name_to_instance = {
            sq.get_tool_name(): sq,
            sh.get_tool_name(): sh,
            sm.get_tool_name(): sm,
        }
        self.model = settings.MODEL
        self.pm = PromptMgr(src_dir=settings.PROMPT_PATH)
        self.sys_msg = self.pm.bind(settings.SYSTEM_PROMPT_FILE_NAME).render()
        self.tools = [x.get_tool_description() for x in self.tool_name_to_instance.values()]
        # TODO(odyash) later: investigate OpenAI's new nomenclature `developer` instead of `system`;
        # https://community.openai.com/t/how-is-developer-message-better-than-system-prompt/1062784
        self.message_history = [{"role": "system", "content": self.sys_msg}]

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
    def replace_message_history(self, message_history, use_tool=True, stream=True):
        """
        TODO(odyash) later (good_first_issue): `stream == False` is not implemented yet; so it has to stay `True`
        """
        self.message_history = [
            {"role": "system", "content": self.sys_msg},
        ] + message_history
        logger.info(f"Original trace is {self.message_logger.trace_id}")
        logger.info(f"Id 1 is {langfuse_context.get_current_trace_id()}")
        # langfuse_context._set_root_trace_id(self.message_logger.trace_id)
        logger.info(f"Id 2 is {langfuse_context.get_current_trace_id()}")
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
        """
        TODO(odyash) later (good_first_issue): `stream == False` is not implemented yet; so it has to stay `True`
        """
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
        while self.message_history[-1]["role"] != "assistant" or "tool_call_id" in self.message_history[-1]:
            try:
                logger.info(
                    f"Process attempt #{count+failures+1} of this message history:\n"
                    + "-" * 60
                    + f"\n{self.message_history}\n"
                    + "-" * 60,
                )
                # This is pretty complicated so leaving a comment.
                # We want to yield from so that we can send the sequence through the input
                # Also use tools only if we haven't tried too many times (failure)
                #  and if the last message was not from the tool (success!)
                use_tool = use_tool and (count < self.settings.MAX_TOOL_TRIES) and self.message_history[-1]["role"] != "tool"
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
                    f"Exception occurred in process_message_history: \n{e}\n",
                )
                logger.warning(traceback.format_exc())
                logger.warning("Retrying in 5 seconds...")
                time.sleep(5)
                if failures >= self.settings.MAX_FAILURES:
                    logger.error("Too many failures, aborting")
                    raise Exception("Too many failures") from e
        self.log()

    def get_completion(self, **kwargs):
        return litellm.completion(**kwargs)

    @observe(as_type="generation")
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
            langfuse_context.update_current_observation(
                output=words,
                metadata={"delta": delta},
            )
            if self.message_logger:
                self.message_logger.log("assistant", words)

        elif response_mode == "tool":
            for tc in tool_calls:
                try:
                    tool_arguments = json.loads(tc["function"]["arguments"])
                    self.process_tool_call(
                        tc["function"]["name"],
                        tool_arguments,
                        tc["id"],
                        tool_definition={
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    )
                except json.JSONDecodeError:
                    logger.warning(
                        f"Failed to parse tool arguments: {tc['function']['arguments']}",
                    )

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

        query: str = tool_arguments["query"]
        tool_instance: SearchQuran | SearchHadith = self.tool_name_to_instance[tool_name]
        results = tool_instance.run_as_list(query)

        # we have to first add this message before any tool response, as mentioned in this source:
        # https://platform.openai.com/docs/guides/function-calling#submitting-function-output
        self.message_history.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"type": "function", "id": tool_id, "function": tool_definition},
                ],
            },
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
            {
                "role": "tool",
                "content": results_str,
                "tool_call_id": tool_id,
            },
        )

        # Note(odyash): If we want to later log the tool response
        # (like we used to do here: https://github.com/ansari-project/ansari-backend/blob/c2bd176ad08b93ddfec4cf63ecadb84f23870a7f/agents/ansari.py#L255)
        # Then we should update the DB's `messages/messages_whatsapp` tables to accomodate for `tool_call_id`/`tool_type`
