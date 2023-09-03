from hermetic.agents.langchain_chat_agent import LangchainChatAgent
from hermetic.core.prompt_mgr import PromptMgr
from tools.kalemat import Kalemat
from langchain.chat_models import ChatOpenAI


from langchain.schema import SystemMessage, HumanMessage

MODEL = 'gpt-4'
NAME = 'ansari-langchain'
class AnsariLangchain(LangchainChatAgent): 
    def __init__(self, env):
        super().__init__(environment = env, id=NAME)
        env.add_agent(NAME, self)
        self.pm = self.env.prompt_mgr
        sys_msg = self.pm.bind('system_msg')
        self.llm = ChatOpenAI(temperature=0, model_name=MODEL, streaming=True)

        self.message_history = [SystemMessage(content=sys_msg.render())]
        
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
            self.message_history.append(HumanMessage(content=expanded_query))
        else: 
            self.message_history.append(HumanMessage(content=inp))

