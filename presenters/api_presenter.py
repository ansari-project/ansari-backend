import copy
import os
import sys
from typing import Dict, List, Optional

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from util.prompt_mgr import PromptMgr


class ApiPresenter:
    def __init__(self, app, agent):
        self.app = app
        self.agent = agent

    def complete(self, messages, message_logger=None):
        print("Complete called.")
        agent = copy.deepcopy(self.agent)
        agent.set_message_logger(message_logger)
        return StreamingResponse(agent.replace_message_history(messages["messages"]))

    def present(self):
        pass
