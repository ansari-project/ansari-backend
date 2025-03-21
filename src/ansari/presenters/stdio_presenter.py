import sys

from ansari.agents.ansari import Ansari


class StdioPresenter:
    def __init__(self, agent: Ansari, skip_greeting=False):
        self.agent = agent
        self.skip_greeting = skip_greeting

    def present(self):
        if not self.skip_greeting:
            sys.stdout.write(self.agent.greet() + "\n")
        sys.stdout.write("> ")
        sys.stdout.flush()
        inp = sys.stdin.readline()
        while inp:
            result = self.agent.process_input(inp)
            # Handle the result which could be either a generator or other iterable
            if result:
                for word in result:
                    if word is not None:
                        sys.stdout.write(word)
                        sys.stdout.flush()
            sys.stdout.write("\n> ")
            sys.stdout.flush()
            inp = sys.stdin.readline()
