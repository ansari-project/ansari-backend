import copy
import time

import discord


class MyClient(discord.Client):
    def __init__(self, agent, intents):
        super().__init__(intents=intents)
        self.agent = agent

    async def on_ready(self):
        print(f"We have logged in as {self.user}")

    async def on_message(self, message):
        if message.author == self.user:
            return
        agent = copy.deepcopy(self.agent)
        print(f"User said: {message.content} and mentioned {message.mentions}")
        st = time.time()
        if (
            isinstance(message.channel, discord.channel.DMChannel)
            or message.content.startswith("<@&1150526640552673324>")
            or (message.mentions and message.mentions[0] and message.mentions[0].name == "Ansari")
        ):
            msg = await message.channel.send(f"Thinking, {message.author}...")
            msg_so_far = ""
            for token in agent.process_input(message.content):
                msg_so_far = msg_so_far + token
                print(f"Message so far: {msg_so_far}")
                et = time.time() - st
                print(f"Elapsed time: {et}")
                if et > 3:
                    print("Enough time has passed. Sending message so far.")
                    if msg_so_far:
                        await msg.edit(content=msg_so_far)
                    else:
                        print(f"For some reason response was empty. {msg_so_far}, {et}")
                    st = time.time()
            if msg_so_far:
                await msg.edit(content=msg_so_far)
            else:
                await msg.edit(content="Something went wrong. Flagging.")
        else:
            print(f"Got a message. Not for me: {message.content}")


class DiscordPresenter:
    def __init__(self, agent, token):
        self.agent = agent
        self.token = token
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = MyClient(agent=agent, intents=intents)

    def present(self):
        self.client.run(self.token)
