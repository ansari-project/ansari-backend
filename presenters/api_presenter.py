import sys
from typing import List, Optional, Dict
from fastapi import FastAPI, APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from util.prompt_mgr import PromptMgr
import uvicorn
import copy
import os


class ApiPresenter(): 
    def __init__(self, app, agent):
        self.app = app
        self.agent = agent
        self.pm = PromptMgr()


    def complete(self, messages):
        print('Complete called.')
        system_prompt = self.pm.bind('system_msg_fn').render()
        agent = copy.deepcopy(self.agent)
        return StreamingResponse(agent.process_message_history(messages.messages, system_prompt))
       
    def present(self):
        pass











    