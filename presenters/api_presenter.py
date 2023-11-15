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


    def complete(self, messages):
        print('Complete called.')
        agent = copy.deepcopy(self.agent)
        return StreamingResponse(agent.replace_message_history(messages['messages']))
       
    def present(self):
        pass











    