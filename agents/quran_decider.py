from hermetic.agents.openai_chat_agent import OpenAIChatAgent
from hermetic.core.prompt_mgr import PromptMgr
from constants import MODEL, RICH_MODEL


class QuranDecider(OpenAIChatAgent): 
    def __init__(self, env):
        super().__init__(model = 'gpt-3.5-turbo', environment = env)

        self.env = env
        self.about_the_quran = self.env.prompt_mgr.bind('about_the_quran')
        
        
    def update_message_history(self, inp): 
        # Add the message with the query in it
        question = self.about_the_quran.render(question=inp)
        print('question is: ', question)
        self.message_history.append({
            'role': 'user', 
            'content': question
            })


