from hermetic.agents.openai_chat_agent import OpenAIChatAgent
from hermetic.core.prompt_mgr import PromptMgr
from tools.kalemat import Kalemat
import json

NAME = 'ansarifn'
class AnsariFn(OpenAIChatAgent): 
    def __init__(self, env):
        super().__init__(model = 'gpt-4',
            environment = env, id=NAME)
        env.add_agent(NAME, self)
        self.kalemat = self.env.tools['kalemat']
        self.pm = self.env.prompt_mgr
        sys_msg = self.pm.bind('system_msg')
        functions = [
            {"name": "search_quran",
            "description": "Search the Qur'an for relevant verses. This should be extracted from the question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The topic to search the Qur'an for ",
                    },
                },
                "required": ["query"],
            },
          }
        ]
        self.functions = functions
    
        self.message_history = [{
            'role': 'system',
            'content': sys_msg.render()
        }]
        
    def greet(self):
        self.greeting = self.pm.bind('greeting')
        return self.greeting.render()
    
    def process_fn_call(self, orig_question, function_name, function_arguments):
        if function_name == 'search_quran':
            args = json.loads(function_arguments)
            query = args['query']
            qt =  self.pm.bind('quran_result')
            results = qt.render(kalemat_results=self.kalemat.run_as_string(query), 
                                orig_question=orig_question)
            # print(f'Function call received! Results: {results}')
            return results

    
    def update_message_history(self, inp):
        # Explicitly do nothing, since we rely on process_message_history
        pass 

