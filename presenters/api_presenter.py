import copy

from fastapi.responses import StreamingResponse


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
