import os
from typing import Dict, List
from fastapi import FastAPI
from presenters.api_presenter import ApiPresenter
from agents.ansari import Ansari
from fastapi.staticfiles import StaticFiles

app = FastAPI()

ansari = Ansari()

port = int(os.getenv('API_SERVER_PORT',8000))


presenter = ApiPresenter(app, ansari)
presenter.present()
app = FastAPI()
@app.post("/api/v1/complete")
def complete(messages: List[Dict]):
    return presenter.complete(messages)