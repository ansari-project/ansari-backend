import hashlib
import logging
import os
import sys
from datetime import date

import litellm

from tools.search_hadith import SearchHadith
from tools.search_vectara import SearchVectara
from tools.search_quran import SearchQuran
from util.prompt_mgr import PromptMgr

logger = logging.getLogger(__name__ + ".AnsariWorkflow")

if not sys.argv[0].endswith("main_api.py"):
    logging_mode = logging.DEBUG
else:
    logging_mode = logging.INFO

logger.setLevel(logging_mode)

# # Uncomment below when logging above doesn't output to std, and you want to see the logs in the console
# console_handler = logging.StreamHandler()
# console_handler.setLevel(logging_mode)
# logger.addHandler(console_handler)


class AnsariWorkflow:
    """
    AnsariWorkflow manages the execution of modular workflow steps for processing user queries.

    This class provides a flexible framework for generating queries, performing searches,
    and generating answers based on the results. It supports customizable workflow steps
    that can be combined in various ways to handle different types of user interactions.

    Attributes:
        tool_name_to_instance (dict): Mapping of tool names to their respective instances.
        model (str): The name of the language model to use.
        sys_msg (str): The system message used for prompts.

    Example usage:
        ansari = AnsariWorkflow(settings)

        # Example 1: Generate query, search, and answer
        workflow_steps = [
            ("gen_query", {"input": "What is the Islamic view on charity?", "target_corpus": "mawsuah"}),
            ("search", {"query_from_prev_output_index": 0, "tool_name": "search_mawsuah"}),
            ("gen_answer", {"input": "What is the Islamic view on charity?", "search_results_indices": [1]})
        ]
        results = ansari.execute_workflow(workflow_steps)

        # Example 2: Direct search and answer
        workflow_steps = [
            ("search", {"query": "zakat calculation", "tool_name": "search_mawsuah"}),
            ("gen_answer", {"input": "How is zakat calculated?", "search_results_indices": [0]})
        ]
        results = ansari.execute_workflow(workflow_steps)
    """

    def __init__(self, settings, message_logger=None, json_format=False):
        self.settings = settings
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
        st = SearchVectara(
            settings.VECTARA_API_KEY.get_secret_value(),
            settings.TAFSIR_VECTARA_CORPUS_KEY,
            settings.TAFSIR_FN_NAME,
            settings.TAFSIR_FN_DESCRIPTION,
            settings.TAFSIR_TOOL_PARAMS,
            settings.TAFSIR_TOOL_REQUIRED_PARAMS,
        )
        self.tool_name_to_instance = {
            sq.get_tool_name(): sq,
            sh.get_tool_name(): sh,
            sm.get_tool_name(): sm,
            st.get_tool_name(): st,
        }
        self.model = settings.MODEL
        self.pm = PromptMgr()
        self.sys_msg = self.pm.bind(settings.SYSTEM_PROMPT_FILE_NAME).render()
        self.tools = [
            x.get_tool_description() for x in self.tool_name_to_instance.values()
        ]
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

    def log(self):
        if not os.environ.get("LANGFUSE_SECRET_KEY"):
            return
        trace_id = self.compute_trace_id()
        logger.info(f"trace id is {trace_id}")

    def _execute_search_step(self, step_params, prev_outputs):
        tool = self.tool_name_to_instance[step_params["tool_name"]]
        if "query" in step_params:
            results = tool.run_as_string(
                step_params["query"], metadata_filter=step_params.get("metadata_filter")
            )
        elif "query_from_prev_output_index" in step_params:
            results = tool.run_as_string(
                prev_outputs[step_params["query_from_prev_output_index"]],
                metadata_filter=step_params.get("metadata_filter")
            )
        else:
            raise ValueError(
                "search step must have either query or query_from_prev_output_index"
            )
        return results

    def _execute_gen_query_step(self, step_params, prev_outputs):
        prompt = f"""Generate 3-5 key terms or phrases for searching the input: '{step_params["input"]}' in the '{step_params["target_corpus"]}' corpus. These search terms should be:

        - Relevant words/phrases that appear in or closely match content in '{step_params["target_corpus"]}'
        - Usable for both keyword and semantic search
        - Given as a simple list without explanation or complete sentences"""
        model_response = litellm.completion(
            model=self.model,
            messages=[
                {"role": "system", "content": self.sys_msg},
                {"role": "user", "content": prompt},
            ],
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
            search_results = "\n---\n".join(
                [prev_outputs[i] for i in step_params["search_results_indices"]]
            )
        prompt = f"""Using {search_results}, compose a response that:
            1. Directly answers the query of the user
            2. Matches user's language/tone
            3. Adheres to your system instructions as Ansari."""
        model_response = litellm.completion(
            model=self.model,
            messages=[
                {"role": "system", "content": self.sys_msg},
                {"role": "system", "content": prompt},
                {"role": "user", "content": step_params["input"]},
            ],
            stream=False,
            timeout=30.0,
            temperature=0.0,
            metadata={"generation-name": "gen-query"},
            num_retries=1,
            response_format=None,
            functions=None,
        )
        return model_response.choices[0].message.content

    def execute_workflow(self, workflow_steps: list[tuple[str, dict]]):
        # this function handles v3 logic
        # the idea is to have Ansari execute a workflow
        # that can be a list of steps
        # allowed steps are:
        # a. search in a corpus
        # b. generate query
        # c. generate answer
        outputs = []
        step_name_to_fn = {
            "search": self._execute_search_step,
            "gen_query": self._execute_gen_query_step,
            "gen_answer": self._execute_gen_answer_step,
        }
        for step_name, step_params in workflow_steps:
            outputs.append(step_name_to_fn[step_name](step_params, outputs))
        return outputs
