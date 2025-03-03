# Unlike other files, the presenter's role here is just to provide functions related to the LLM


from fastapi.responses import StreamingResponse

from ansari.agents import Ansari, AnsariClaude
from ansari.ansari_db import MessageLogger


class ApiPresenter:
    def __init__(self, app, agent: Ansari):
        self.app = app
        self.settings = agent.settings

    def complete(self, messages: dict, message_logger: MessageLogger = None):
        print("Complete called.")
        if self.settings.AGENT == "Ansari":
            agent = Ansari(settings=self.settings, message_logger=message_logger)
        elif self.settings.AGENT == "AnsariClaude":
            agent = AnsariClaude(settings=self.settings, message_logger=message_logger)

        return StreamingResponse(agent.replace_message_history(messages["messages"]))

    def present(self):
        pass
