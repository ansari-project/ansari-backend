from hermetic.agents.openai_chat_agent import OpenAIChatAgent
from hermetic.core.prompt_mgr import PromptMgr
from constants import MODEL, RICH_MODEL


class Ansari(OpenAIChatAgent): 
    def __init__(self, env):
        super().__init__(model = 'gpt-4',
            environment = env)
        pm = self.env.prompt_mgr
        self.greeting = pm.bind('greeting')
        self.sys_msg = pm.bind('system_msg')
        

        self.message_history = [{
            'role': 'system',
            'content': self.sys_msg.render()
        }]
        
    def greet(self):
        return self.greeting.render()
    
    def update_message_history(self, inp): 

        self.message_history.append({
            'role': 'user', 
            'content': inp
            })


