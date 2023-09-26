import logging
from typing import Union

import tiktoken
from hermetic.agents.langchain_chat_agent import LangchainChatAgent
from hermetic.core.prompt_mgr import PromptMgr
from langchain.callbacks import OpenAICallbackHandler

from tools.kalemat import Kalemat
from langchain.chat_models import ChatOpenAI


from langchain.schema import SystemMessage, HumanMessage, AIMessage

LOG = logging.getLogger(__name__)

FLAG_INSTRUCTION = """'\n
The user wanted to flag an issue. Ask them the cause: wrong, confusing, funny or impressive. 
Also ask them for their email address but make it clear it is optional.\n'
"""

MODEL = 'gpt-4'
NAME = 'ansari-langchain'
class AnsariLangchain(LangchainChatAgent):
    def __init__(self, env):
        super().__init__(environment = env, id=NAME)
        env.add_agent(NAME, self)
        self.pm = self.env.prompt_mgr
        sys_msg = self.pm.bind('system_msg')

        self.llm_8k = ChatOpenAI(temperature=0, model_name=MODEL, streaming=True)
        self.llm_32k = ChatOpenAI(temperature=0, model_name="gpt-4-32k", streaming=True)

        self.tiktoken_encoding = tiktoken.encoding_for_model(MODEL)
        self.message_history_token_counts = []
        self.message_history_tokens_total = 0
        self.message_history = [SystemMessage(content=sys_msg.render())]

    @property
    def llm(self):
        """There are two GTP-4 models. Choose which one to use, depending on the message history length, and return it.

        See: https://help.openai.com/en/articles/7127966-what-is-the-difference-between-the-gpt-4-models
        """
        if self.message_history_tokens_total < 8000:
            return self.llm_8k
        elif self.message_history_tokens_total < 32000:
            return self.llm_32k
        else:
            LOG.debug(
                f"The conversation became too long, and we should summarize it: {self.message_history_tokens_total}."
            )
            raise Exception("The conversation became too long")

    def greet(self):
        self.greeting = self.pm.bind('greeting')
        return self.greeting.render()

    def update_message_history(self, inp):

        quran_decider = self.env.agents['quran_decider']
        result = quran_decider.process_all(inp)
        print(f'quran decider returned {result}')
        if 'Yes' in result:
            # Do a secondary search here.
            query_extractor = self.env.agents['query_extractor']
            query = query_extractor.process_all(inp)
            print(f'query extractor returned {query}')
            kalemat = self.env.tools['kalemat']
            results = kalemat.run_as_string(query)
            print(f'kalemat returned {results}')
            eq = self.pm.bind('ansari_expanded_query')
            expanded_query = eq.render(quran_results=results, user_question=inp)
            #print(f'expanded query is {expanded_query}')
            if ' flag ' in inp:
                expanded_query = expanded_query + FLAG_INSTRUCTION
            self.message_history.append(HumanMessage(content=expanded_query))
        else:
            if ' flag ' in inp:
                inp = inp + FLAG_INSTRUCTION
            self.message_history.append(HumanMessage(content=inp))

    def on_message_history_append(self,  msg: Union[AIMessage, HumanMessage, SystemMessage]):
        """Add the number of tokens in the new message to the counts of tokens and to the total tokens of the history.

        Follows https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
        """
        num_tokens = len(self.tiktoken_encoding.encode(msg.content))
        self.message_history_token_counts.append(num_tokens)
        self.message_history_tokens_total += num_tokens

