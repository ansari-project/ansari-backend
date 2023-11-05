import sys
from hermetic.core.agent import Agent
from hermetic.core.environment import Environment


class StdioPresenter:

    def present(self, env: Environment): 
        agent = env.primary()
        sys.stdout.write(agent.greet() + '\n') 
        while True: 
            sys.stdout.write('> ')
            inp = input()
            for word in agent.process_input(inp):
                sys.stdout.write(word)
                sys.stdout.flush()
            sys.stdout.write('\n')