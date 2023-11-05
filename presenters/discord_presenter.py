import discord
from dotenv import load_dotenv
import os
from agents.ansari_langchain import AnsariLangchain
from agents.quran_decider import QuranDecider
from agents.query_extractor import QueryExtractor
from tools.kalemat import Kalemat
from hermetic.core.environment import Environment
from hermetic.stores.file_store import FileStore
from hermetic.core.prompt_mgr import PromptMgr
from hermetic.core.presenter import Presenter
import time
import copy


load_dotenv('/Users/mwk/Development/ansari/.env')

class MyClient(discord.Client):
    def __init__(self, env, intents):
        self.env = env
        super().__init__(intents=intents)


    async def on_ready(self):
        print(f'We have logged in as {self.user}')

    async def on_message(self, message):
        if message.author == self.user:
            return
        agent = copy.deepcopy(self.env.agents[self.env.primary_agent])
        print(f'User said: {message.content} and mentioned {message.mentions}')
        st = time.time() 
        if isinstance(message.channel,discord.channel.DMChannel) or \
        message.content.startswith('<@&1150526640552673324>') or \
        (message.mentions and message.mentions[0] and message.mentions[0].name == 'Ansari'):
            msg = await message.channel.send(f'Thinking, {message.author}...')
            msg_so_far = '' 
            for token in agent.process_input(message.content): 
                msg_so_far = msg_so_far + token
                print(f'Message so far: {msg_so_far}')
                et = time.time() - st
                print(f'Elapsed time: {et}')
                if et > 3:
                    print('Enough time has passed. Sending message so far.')
                    if msg_so_far:
                        await msg.edit(content=msg_so_far)
                    else: 
                        print(f'For some reason response was empty. {msg_so_far}, {et}')
                    st = time.time()
            if msg_so_far:
                await msg.edit(content=msg_so_far)
            else: 
                await msg.edit(content='Something went wrong. Flagging.')
        else:
            print(f'Got a message. Not for me: {message.content}')
    

class DiscordPresenter(Presenter):
    def __init__(self, env, token):
        self.env = env
        self.token = token
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = MyClient(env = self.env, intents=intents)

    def present(self):
        self.client.run(self.token)




'''
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    print('User said: ', message.content)
    await message.channel.send(f'Hello! You said: {message.content}')

client.run(os.getenv('DISCORD_TOKEN'))
'''

env = Environment(store =  FileStore(root_dir = 'ansari-stores'), 
                  prompt_mgr = PromptMgr(hot_reload=True))

# This work involves 3 agents, with Ansari as primary. 
ansari = AnsariLangchain(env)
env.set_primary_agent('ansari-langchain')
decider = QuranDecider(env)
query_extractor = QueryExtractor(env)

# We also use one tool, which is Kalemat lookup 
kalemat = Kalemat(env)
    
 

presenter = DiscordPresenter(env=env, token=os.getenv('DISCORD_TOKEN'))

# This starts the UI. 
presenter.present()
