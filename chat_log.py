# Class for storing the log of openAI chat

from typing import Dict, List, Optional, Bas
from uuid import UUID
from langchain.schema import AIChatMessage, HumanChatMessage, SystemChatMessage, ChatMessage
from pydantic import BaseModel
import tiktoken

class ChatLog(BaseModel):
    """
    Stores a log of chat messages. It does this
    in LangChain Format
    """
    def __init__(self, session_id):
        self.session_id = session_id
        self.enc = tiktoken.encoding_for_model("gpt-4")
        self.messages: List[ChatMessage] = []
        # Lengths of messages in tokens
        self.message_lengths: List[int] = []

    def add_system_message(self,message : str):
        self.messages.append(SystemChatMessage(text=message))
        self.message_lengths.append(self.enc.encode(message).length)

    def add_user_message(self, message: str):
        self.messages.append(HumanChatMessage(text=message))
        self.message_lengths.append(self.enc.encode(message).length)

    def add_ai_message(self, message: str):
        self.messages.append(AIChatMessage(text=message))
        self.message_lengths.append(self.enc.encode(message).length)

    def extract_gradio_messages(self):
        """
        Extracts the messages in a format that can be
        used by gradio. 
        
        Gradio expects a list of lists, with each inner list
        being a pair of strings where the first element is the 
        user message and the last one is the response. 
        """
        #Step 1: filter out all system messages
        gradio_messages_unpaired = []
        for message in self.messages:
            if isinstance(message, SystemChatMessage):
                continue
            elif isinstance(message, AIChatMessage):
                gradio_messages_unpaired.append([message.text, message.response])
            elif isinstance(message, HumanChatMessage):
                gradio_messages_unpaired.append([message.text, message.response])
            else:
                raise Exception(f"Unknown message type: {type(message)}")

        # Step 2: ensure that we start with user message. If we do not, prepend
        # a None
        if len(gradio_messages_unpaired) > 0 and not isinstance(self.messages[0], HumanChatMessage):
            # prepend a None
            gradio_messages_unpaired.insert(0, None)

        # Step 3: If the final message is not a AIChatMessage, append a None
        if len(gradio_messages_unpaired) > 0 and not isinstance(self.messages[-1], AIChatMessage):
            gradio_messages_unpaired.append(None)
        
        # Step 4: Pair up the messages
        gradio_messages = []
        for i in range(0, len(gradio_messages_unpaired), 2):
            gradio_messages.append(gradio_messages_unpaired[i:i+2])

        return gradio_messages
    
    def extract_most_context_possible(self, max_tokens):
        # Quick check to see if we can fit the whole thing
        if sum(self.message_lengths) <= max_tokens:
            return self.messages
        else:
            # We have to trim the messages
            # We do this by starting at the context start message
            # and dropping it until it is less than max_tokens
            # We must always include the first message, 
            # the system message
            amount_to_trim = sum(self.message_lengths) - max_tokens - self.message_lengths[0]
            trimmed_length = 0
            for i in range(1, len(self.messages)):
                if trimmed_length > amount_to_trim:
                    break
                else:
                    trimmed_length += self.message_lengths[i]
            
            return self.messages[0] + self.message_lengths[:i+1]
