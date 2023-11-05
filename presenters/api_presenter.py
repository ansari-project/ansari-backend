import sys
from typing import List, Optional, Dict
from fastapi import FastAPI, APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from util.prompt_mgr import PromptMgr
import uvicorn
import copy
import os


class Messages(BaseModel):
    messages: List[Dict]

class ApiPresenter(BaseModel): 
    def __init__(self, app, port):
        self.port = port
        self.app = app
        self.pm = PromptMgr()


    def complete(self, messages: Messages):
        print('Complete called.')
        system_prompt = self.pm.bind('system_msg_fn').render()
        ans = AnsariFn()
        return StreamingResponse(ans.process_message_history(messages.messages, system_prompt))
       
    def present(self):
        pass

app = FastAPI()

tools = {
    'kalemat': Kalemat()
}

port = int(os.getenv('API_SERVER_PORT',8000))
@app.post("/api/v1/complete")
def complete(messages: Messages):
    return presenter.complete(messages)

presenter = ApiPresenter(app, port)
presenter.present()










    