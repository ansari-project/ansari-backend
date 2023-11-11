import sys
from agents.ansari import Ansari

class StdioPresenter:
    def __init__(self, agent):
        self.agent = agent

    def present(self): 
        sys.stdout.write(self.agent.greet() + '\n') 
        sys.stdout.write('> ')
        sys.stdout.flush()
        inp = sys.stdin.readline()
        while inp: 
            for word in self.agent.process_input(inp):
                if word is not None: 
                    sys.stdout.write(word)
                    sys.stdout.flush()
            sys.stdout.write('\n> ')
            inp = sys.stdin.readline()



