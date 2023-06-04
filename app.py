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

END = '-- END --'
GREETING ="""Assalamu alaikum! My name is Ansari. I can help you with your questions about Islam.
Ask me about: 
- Dua to make in particular situation
- Spiritual remedies for challenges you are facing. 
- Islamic perspectives on topics

But I still get things wrong sometimes. It is always best to consult a real Islamic Scholar. """

with gr.Blocks() as demo:
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
            self.q.put(token)
        
        def on_llm_end(self, response, *, run_id, parent_run_id, **kwargs):
            self.q.put(END)

    history = [["", GREETING]]
    chatbot = gr.Chatbot(value=history)
    msg = gr.Textbox() 
    q = SimpleQueue()
    oai = PromptLayerChatOpenAI(streaming=True, temperature=0, model_name='gpt-3.5-turbo',
                    callbacks=[MyCBH(q)], pl_tags=['ansari'])
    openai_history = [SystemMessage(content="""
    You are a helpful assistant. Your name is Ansari. You help Muslims become stronger in my faith. 
    Respond to questions with information drawn from the Hadith 
    and Qur'an and from the opinions of great scholars in the Sunni Islamic tradition like 
    Al Ghazali, Ibn Taymiyah, Imam Shafiee, Imam Nawawi, Imam Abu Hanifah, Ibn Hajr al Asqalani, 
    Ibn Hazm and others. Be gentle, forbearing and non-judgemental. 

    Be concise in your answers. 
    """),
    AIMessage(content=GREETING)]


    def user(user_message, history):
        openai_history.append(HumanMessage(content=user_message))
        return gr.update(value="", interactive=False), history + [[user_message, None]]

    async def bot(history):
        #print(f'History is {history}')
        history[-1][1] =''
        thread =  Thread(target = oai.predict_messages, kwargs = {'messages': openai_history})
        thread.start() 
        token = q.get() # Get rid of crap token. 
        while True: 
            token = q.get()
            if token == END:
               break
            history[-1][1] += token
            yield history
        openai_history.append(AIMessage(content=history[-1][1]))
        print(f'OpenAI history is: {openai_history}')
        print(f'Num tokens is: {oai.get_num_tokens_from_messages(openai_history)}')

    response = msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
        bot, chatbot, chatbot
    ).then(lambda: gr.update(interactive=True), None, [msg], queue=False)

demo.queue(concurrency_count=16)
demo.launch()