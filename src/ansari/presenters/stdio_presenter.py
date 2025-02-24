import sys


class StdioPresenter:
    def __init__(self, agent, skip_greeting=False):
        self.agent = agent
        self.skip_greeting = skip_greeting

    def present(self):
        if not self.skip_greeting:
            sys.stdout.write(self.agent.greet() + "\n")
        sys.stdout.write("> ")
        sys.stdout.flush()
        inp = sys.stdin.readline()
        while inp:
            for word in self.agent.process_input(inp):
                if word is not None:
                    sys.stdout.write(word)
                    sys.stdout.flush()
            sys.stdout.write("\n> ")
            inp = sys.stdin.readline()
