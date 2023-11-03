import sys
from typing import List, Optional, Dict
from fastapi import FastAPI, APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from agents.ansari_fn import AnsariFn
from agents.quran_decider import QuranDecider
from tools.kalemat import Kalemat
from agents.query_extractor import QueryExtractor
from tools.kalemat import Kalemat
from hermetic.core.agent import Agent
from hermetic.core.environment import Environment
from hermetic.core.presenter import Presenter
from hermetic.core.environment import Environment
from hermetic.stores.file_store import FileStore
from hermetic.core.prompt_mgr import PromptMgr
import uvicorn
import copy
import os


class Messages(BaseModel):
    messages: List[Dict]

class ApiPresenter(Presenter): 
    def __init__(self, 
                env: Environment, app, port):
        self.env = env
        self.port = port
        self.app = app
        self.router = APIRouter()
        self.router.add_api_route("/api/v1/complete", self.complete, methods=["POST"])


    def complete(self, messages: Messages):
        print('Complete called.')
        pm = self.env.prompt_mgr
        system_prompt = pm.bind('system_msg_fn').render()
        myansari = copy.deepcopy(ansari)
        return StreamingResponse(myansari.process_message_history(messages.messages, system_prompt))
       

    def present(self):
        pass


env = Environment(store =  FileStore(root_dir = 'ansari-stores'), 
                  prompt_mgr = PromptMgr(hot_reload=True))


# This work involves 3 agents, with Ansari as primary. 
kalemat = Kalemat(env)
ansari = AnsariFn(env)
env.set_primary_agent('ansarifn')
app = FastAPI()

port = int(os.getenv('API_SERVER_PORT',8000))
@app.post("/api/v1/complete")
def complete(messages: Messages):
    return presenter.complete(messages)

presenter = ApiPresenter(env, app, port)
presenter.present()
#uvicorn.run(app, host="0.0.0.0", port=port)










    