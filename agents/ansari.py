from hermetic.agents.openai_chat_agent import OpenAIChatAgent
from hermetic.core.prompt_mgr import PromptMgr
from tools.kalemat import Kalemat

NAME = 'ansari'
class Ansari(OpenAIChatAgent): 
    def __init__(self, env):
        super().__init__(model = 'gpt-4',
            environment = env, id=NAME)
        env.add_agent(NAME, self)
        self.pm = self.env.prompt_mgr
        sys_msg = self.pm.bind('system_msg')
        

        self.message_history = [{
            'role': 'system',
            'content': sys_msg.render()
        }]
        
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
            print(f'expanded query is {expanded_query}')
            if ' flag ' in inp:
                expanded_query = expanded_query + '\nIt seems the user asked to flag something. Ask them what they want to flag and why.\n'
            self.message_history.append({
                'role': 'user', 
                'content': expanded_query
                })

        else: 
            print(f'In else clause {inp}')
            )
            if ' flag ' in inp:
                print(f'In flag clause {inp}')
                inp = inp + '\nIt seems the user asked to flag something. Ask them what they want to flag and why.\n'
            self.message_history.append({
                'role': 'user', 
                'content': inp
                })


