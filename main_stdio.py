import os
from datetime import datetime
from agents.ansari import Ansari
from presenters.stdio_presenter import StdioPresenter

if __name__ == '__main__':
    os.environ['TO_STDIO'] = '1'
    agent = Ansari()
    presenter = StdioPresenter(agent)
    presenter.present()
