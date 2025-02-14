# Unlike other files, the presenter's role here is just to provide functions related to the LLM

import copy

from fastapi.responses import StreamingResponse

from ansari.agents import Ansari
from ansari.ansari_db import MessageLogger


class ApiPresenter:
    def __init__(self, app, agent: Ansari):
        self.app = app
        self.agent = agent

    def complete(self, messages: dict, message_logger: MessageLogger = None):
        print("Complete called.")
        agent = copy.deepcopy(self.agent)
        agent.set_message_logger(message_logger)
        return StreamingResponse(agent.replace_message_history(messages["messages"]))

    def present(self):
        pass
