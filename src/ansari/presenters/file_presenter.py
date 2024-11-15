import copy
import os


class FilePresenter:
    def __init__(self, agent):
        self.agent = agent

    def present(self, input_file_path, output_file_path):
        # Read lines from input file
        with open(input_file_path) as input_file:
            lines = input_file.readlines()

        # Send each line to agent and get result
        with open(output_file_path, "w+") as output_file:
            for line in lines:
                print(f"Answering: {line}")
                agent = copy.deepcopy(self.agent)
                # Drop none that occurs between answers.
                result = [tok for tok in agent.process_input(line) if tok]
                answer = "".join(result)
                (question, answer) = (line.strip(), answer)
                output_file.write(f"## {question}\n\n{answer}\n\n")
                output_file.flush()
            print(f"Result saved to {os.path.abspath(output_file_path)}")
