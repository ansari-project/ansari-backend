import sys
from typing import List, Optional, Dict
from fastapi import FastAPI, APIRouter
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


class Messages(BaseModel):
    messages: List[Dict]

class ApiPresenter(Presenter): 
    def __init__(self, 
                env: Environment):
        self.env = env
        self.router = APIRouter()
        self.router.add_api_route("/api/v1/complete", self.complete, methods=["POST"])


    def complete(self, messages: Messages):
        myansari = copy.deepcopy(ansari)
        return myansari.process_message_history(messages.messages)
       

    def present(self):
        self.agent = self.env.agents[self.env.primary_agent]
        app = FastAPI()
        app.include_router(self.router)
        uvicorn.run(app, host="0.0.0.0", port=8000)


env = Environment(store =  FileStore(root_dir = 'ansari-stores'), 
                  prompt_mgr = PromptMgr(hot_reload=True))


# This work involves 3 agents, with Ansari as primary. 
kalemat = Kalemat(env)
ansari = AnsariFn(env)
env.set_primary_agent('ansarifn')

presenter = ApiPresenter(env)
presenter.present()









    