from typing import Any, Optional
from uuid import UUID
import gradio as gr
from rich import print
import re
import random
import time
import asyncio
from asyncio import Queue
from threading import Thread
from queue import SimpleQueue
from langchain.chat_models import ChatOpenAI, PromptLayerChatOpenAI
from langchain.llms import OpenAI
from langchain.callbacks.base import AsyncCallbackHandler, BaseCallbackHandler
from langchain import PromptTemplate, LLMChain
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.vectorstores.vectara import Vectara
from langchain.schema import (
    AIMessage,
    HumanMessage,
    LLMResult,
    SystemMessage
)
import uuid

MODEL = 'gpt-3.5-turbo'
MAX_LENGTH = 3500 # have to leave some space for answers or they get chopped off midway. 

END = '-- END --'

SYSTEM_MESSAGE = """
You are a helpful assistant. Your name is Ansari. You help Muslims become stronger in their faith. 
Respond to questions with information drawn from the Hadith 
and Qur'an and from the opinions of great scholars in the Sunni Islamic tradition like 
Al Ghazali, Ibn Taymiyah, Imam Shafiee, Imam Nawawi, Imam Abu Hanifah, Ibn Hajr al Asqalani, 
Ibn Hazm and others. You also draw from the work of modern Islamic scholars including Yusuf
Al Qaradawi, Yasir Qadhi, Ma'in Al Qudah, Shu'aib Al Arnaout, Hamza Yusuf, Zaid Shakir and Yaser Birjas. 

Be gentle, forbearing and non-judgemental. 

Be particularly careful about something is obligatory or prohibited. Proofs are required to say something 
is obligatory or prohibited. The proofs must directly support the assertion. 

For example, if someone asks if washing the knees are part of wudu, there must be Qur'an or Hadith
that specifically mentions washing the knees.

Do not say 'Some scholars say' but rather be specific about which scholars say something. 

Be concise. Do not embellish.  

"""

GREETING ="""Assalamu alaikum! My name is Ansari. I can help you with your questions about Islam.
Ask me about: 
- Dua to make in particular situation
- Spiritual remedies for challenges you are facing. 
- Islamic perspectives on topics

But I still get things wrong sometimes. It is always best to consult a real Islamic Scholar. """


CSS ="""
.contain { display: flex; flex-direction: column; }
#component-0 { height: 100%; }
#chatbot { flex-grow: 1; }
"""

with gr.Blocks(title='Ansari', css=CSS) as demo:

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

    def pp_ayah(doc_score):
        doc, score = doc_score
        # Ignore title matches
        if 'is_title' in doc.metadata and doc.metadata['is_title'] == 'true': 
            return '' 
        #ignore low scoring matches. 
        if score < 0.2:
            print(f'Dropped {doc.page_content} because of score: {score}')
            return ''
        print(f'Doc is {doc}')
        verse_number = doc.metadata['title'] #re.findall('\d+:\d+', doc.metadata["breadcrumb"])[0]
        #print('verse number is: ' + verse_number)
        content = re.sub('\d+:\d+$', '', doc.page_content)
        #print(f'Content is: {content}')
        result = f'Ayah: {verse_number}\n Content: {content}\n'
        return result
    
    def lookup_quran(question):
        vs = Vectara()
        results = vs.similarity_search_with_score(
            query=question,
            lambd_val=0.1)
        #print(f'Results are {results}')
        rstring = '\n'.join([pp_ayah(r) for r in results])
        return rstring
        

    my_id = gr.State(get_new_id)
    history = gr.State([['', GREETING]])
    openai_history = gr.State([SystemMessage(content=SYSTEM_MESSAGE), AIMessage(content=GREETING)])
    gr.Markdown(value="**News 2023-06-18**: Added automatic Qur'an search. Sign up for the [Google Group](http://walee.dk/asu) for updates/discussion!")
    chatbot_ui = gr.Chatbot(value=[[None, GREETING]],elem_id="chatbot")
    msg_ui = gr.Textbox(show_label=False) 


    state_vars = [history, openai_history, my_id]
    def determine_quranic(question):
        oai = OpenAI(temperature=0, model_name=MODEL)
        prompt = 'Determine if the following question is about the Qur\'an. ' \
                        'Examples: \n\n' \
                        'Question: Does the Qur\'an mention rubies?\nAnswer: Yes\n\n'  \
                        "Question: What does the Qur\'an say about the day of Judgement?\nAnswer: Yes\n\n" \
                        'Question: What does Islam say about birthdays?\nAnswer: No\n\n' \
                        'Question: I am tired.\nAnswer: No\n\n' \
                        'Question: Is washing the knees obligatory?\n Answer: No\n\n' \
                        'Question: ' + question + '\n' \
                        'Answer: '
        print(f'Prompt is: {prompt}')
        quranic = oai.predict(prompt)
        print(f'Result is: {quranic}')
        return quranic.startswith('Yes')
    
    def quranic_results(user_message):
        oai = OpenAI(temperature=0, model_name=MODEL)
        prompt = f"""Extract the best query to use for a keyword search about the Qur\'an from the following question.

Do not include the word Qur'an.
Examples: 

Question: Does the Qur'an mention rubies?
Answer: rubies

Question: What does the Qur'an say about adultery?
Answer: Adultery

Question: {user_message} 
Answer: """ 
        
        topic = oai.predict(prompt)
        print(f'gpt-3.5-turbo recommended topic is {topic}')
        quran_results = lookup_quran(topic)
        quran_message = """Here is some context from the Qur'an.

""" + quran_results + """

Use this context to answer the next question from the user.
Do not use external sources unless you are highly confident. 
Include the Arabic text and the English translation.

Examples: 

Question: Does the Qur'an mention corals? 

Answer: Yes, the Qur'an mentions corals in ayah 55:22 in ayah 55:58.

Ayah: 55:22
Arabic: مِنْهُمَا يَخْرُجُ اللُّؤْلُؤُ وَالْمَرْجَانُ
English: From both of them emerge pearl and coral.

Ayah 55:58
Arabic: كَأَنَّهُنَّ ٱلْيَاقُوتُ وَٱلْمَرْجَان  
English: As if they were rubies and coral.

Question: Where in the Qur'an are elephants discussed? 

Answer: The Qur'an discusses elephants in: 

Ayah: 105:1
Arabic: أَلَمْ تَرَ كَيْفَ فَعَلَ رَبُّكَ بِأَصْحَابِ الْفِيلِ
English: Have you not seen how your Lord dealt with the companions of the elephant?

Question: """ + user_message
        
        return quran_message

    def user(user_message, chatbot_ui, history, openai_history, my_id):
        openai_history.append(HumanMessage(content=user_message))
        quranic = determine_quranic(user_message)
        print(f'oai returned {quranic}')
        if quranic: 
            quran_message = quranic_results(user_message)
            openai_history.append(AIMessage(content=quran_message))
        return gr.update(value=""), history + [[user_message, None]],  history + [[user_message, None]], openai_history, my_id

    def bot(chatbot_ui, history, openai_history, my_id):
        q = SimpleQueue() 
        oai = PromptLayerChatOpenAI(streaming=True, temperature=0, model_name=MODEL,
                    callbacks=[MyCBH(q)], pl_tags=[f'ansari-{my_id}'])
        #print(f'History is {history}')
        history[-1][1] =''
        # Now we have to drop our history
        num_tokens = oai.get_num_tokens_from_messages(openai_history)
        print(f'Num tokens is: {num_tokens}')
        # Loop repeatedly cutting history til it's less
        # Note: There is no need to trim the history. 
        # We just need to trim the openAI history. 
        while num_tokens > MAX_LENGTH: 
            openai_history.pop(0)
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
        #print(f'OpenAI history is: {openai_history}')
        return chatbot_ui, history, openai_history, my_id


    response = msg_ui.submit(user, 
                             [msg_ui, chatbot_ui] + state_vars, 
                             [msg_ui, chatbot_ui] + state_vars, 
                             queue=False).then(
        bot, [chatbot_ui] + state_vars, [chatbot_ui] + state_vars
    )

demo.queue(concurrency_count=8)
demo.launch(favicon_path='./favicon.ico')