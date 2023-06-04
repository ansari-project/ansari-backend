from typing import Any, Optional
from uuid import UUID
import gradio as gr
import random
import time
import asyncio
from asyncio import Queue
from threading import Thread
from queue import SimpleQueue
from langchain.chat_models import ChatOpenAI, PromptLayerChatOpenAI
from langchain.callbacks.base import AsyncCallbackHandler, BaseCallbackHandler
from langchain import PromptTemplate, LLMChain
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.schema import (
    AIMessage,
    HumanMessage,
    LLMResult,
    SystemMessage
)
import uuid

MAX_LENGTH = 3500 # have to leave some space for answers or they get chopped off midway. 

END = '-- END --'

SYSTEM_MESSAGE = """
You are a helpful assistant. Your name is Ansari. You help Muslims become stronger in my faith. 
Respond to questions with information drawn from the Hadith 
and Qur'an and from the opinions of great scholars in the Sunni Islamic tradition like 
Al Ghazali, Ibn Taymiyah, Imam Shafiee, Imam Nawawi, Imam Abu Hanifah, Ibn Hajr al Asqalani, 
Ibn Hazm and others. Be gentle, forbearing and non-judgemental. 

Be concise in your answers. 
"""

GREETING ="""Assalamu alaikum! My name is Ansari. I can help you with your questions about Islam.
Ask me about: 
- Dua to make in particular situation
- Spiritual remedies for challenges you are facing. 
- Islamic perspectives on topics

But I still get things wrong sometimes. It is always best to consult a real Islamic Scholar. """

with gr.Blocks() as demo:
    def get_new_id():
        return str(uuid.uuid4())
    
    class MyCBH(BaseCallbackHandler):
        def __init__(self, q):
            self.q = q

        def on_llm_new_token(
            self,
            token,
            *,
            run_id,
            parent_run_id = None,
            **kwargs,
        ) -> None:
            self.q.put(token,my_id)
        
        def on_llm_end(self, response, *, run_id, parent_run_id, **kwargs):
            self.q.put(END, my_id)

    my_id = gr.State(get_new_id)
    history = gr.State([['', GREETING]])
    openai_history = gr.State([SystemMessage(content=SYSTEM_MESSAGE), AIMessage(content=GREETING)])    
    chatbot_ui = gr.Chatbot(value=[[None, GREETING]])
    msg_ui = gr.Textbox() 


    state_vars = [history, openai_history, my_id]
    def user(user_message, chatbot_ui, history, openai_history, my_id):
        openai_history.append(HumanMessage(content=user_message))
        return gr.update(value=""), history + [[user_message, None]],  history + [[user_message, None]], openai_history, my_id

    def bot(chatbot_ui, history, openai_history, my_id):
        q = SimpleQueue() 
        oai = PromptLayerChatOpenAI(streaming=True, temperature=0, model_name='gpt-3.5-turbo',
                    callbacks=[MyCBH(q)], pl_tags=[f'ansari-{my_id}'])
        #print(f'History is {history}')
        history[-1][1] =''
        # Now we have to drop our history
        num_tokens = oai.get_num_tokens_from_messages(openai_history)
        print(f'Num tokens is: {num_tokens}')
        # Loop repeatedly cutting history til it's less
        while num_tokens > MAX_LENGTH: 
            openai_history.pop(0)
            history.pop(0)
            num_tokens = oai.get_num_tokens_from_messages(openai_history)
            print(f'Reduced num_tokens to {num_tokens}')

        thread =  Thread(target = oai.predict_messages, kwargs = {'messages': openai_history})
        thread.start() 
        while True: 
            token = q.get()
            if token == END:
               break
            history[-1][1] += token
            yield history, history, openai_history, my_id
        openai_history.append(AIMessage(content=history[-1][1]))
        print(f'OpenAI history is: {openai_history}')
        return chatbot_ui, history, openai_history, my_id


    response = msg_ui.submit(user, 
                             [msg_ui, chatbot_ui] + state_vars, 
                             [msg_ui, chatbot_ui] + state_vars, 
                             queue=False).then(
        bot, [chatbot_ui] + state_vars, [chatbot_ui] + state_vars
    )

demo.queue(concurrency_count=8)
demo.launch()