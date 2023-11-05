import sys
from agents.ansari import Ansari

class StdioPresenter:
    def __init__(self, agent):
        self.agent = agent

    def present(self, agent): 
        self.agent = agent
        sys.stdout.write(agent.greet() + '\n') 
        sys.stdout.write('> ')
        sys.stdout.flush()
        inp = sys.stdin.readline()
        while inp: 
            for word in agent.process_input(inp):
                if word is not None: 
                    sys.stdout.write(word)
                    sys.stdout.flush()
                else: 
                    print('None received.')
            sys.stdout.write('\n> ')
            inp = sys.stdin.readline()



