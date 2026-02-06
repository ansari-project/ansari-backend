import sys

from ansari.agents.ansari import Ansari


class StdioPresenter:
    def __init__(self, agent: Ansari, skip_greeting=False, stream=False):
        self.agent = agent
        self.skip_greeting = skip_greeting
        self.stream = stream

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
                print("Model response:")
                if self.stream:
                    # Stream output word by word
                    for word in result:
                        sys.stdout.write(word)
                        sys.stdout.flush()
                else:
                    # Collect the entire response and output at once
                    complete_response = "".join([word for word in result])
                    sys.stdout.write(complete_response)
                    sys.stdout.flush()
            sys.stdout.write("\n> ")
            sys.stdout.flush()
            inp = sys.stdin.readline()
