import csv
import logging
import os
from typing import Tuple

from ansari.agents.ansari_workflow import AnsariWorkflow


class AyahFilePresenter:
    def __init__(self, settings, use_query_generation: bool = False, answer_column: str = "answer"):
        self.settings = settings
        self.use_query_generation = use_query_generation
        self.answer_column = answer_column

    def _parse_ayah_reference(self, ayah_ref: str) -> Tuple[int, int]:
        """Parse a surah:ayah reference into separate numbers.

        Args:
            ayah_ref: String in format "surah:ayah"

        Returns:
            Tuple of (surah_num, ayah_num)

        Raises:
            ValueError: If format is invalid or empty
        """
        if not ayah_ref or not ayah_ref.strip():
            raise ValueError("Empty ayah reference")

        try:
            surah_str, ayah_str = ayah_ref.strip().split(":")
            return int(surah_str), int(ayah_str)
        except ValueError:
            raise ValueError(f"Invalid ayah reference format: {ayah_ref}. Expected format: surah:ayah (e.g. 1:1)")

    def present(self, input_file_path: str, output_file_path: str):
        try:
            # First pass: read header to get all field names
            with open(input_file_path, newline="") as input_file:
                # Skip empty lines and get header
                for line in input_file:
                    if line.strip():  # First non-empty line is header
                        reader = csv.reader([line])
                        header = next(reader)
                        if len(header) < 2:
                            logging.error("Input CSV must contain at least two columns")
                            return
                        break
                else:
                    logging.error("Empty input file")
                    return

                # Create fieldnames, preserving original names
                fieldnames = header
                if self.answer_column not in fieldnames:
                    fieldnames = fieldnames + [self.answer_column]

            # Second pass: process all rows
            with open(input_file_path, newline="") as input_file:
                reader = csv.reader(input_file)

                # Open output file and write
                with open(output_file_path, "w", newline="") as output_file:
                    writer = csv.writer(output_file)
                    writer.writerow(fieldnames)

                    for row in reader:
                        # Skip empty lines
                        if not any(row):
                            continue

                        try:
                            # Get values from first and second columns using column positions
                            ayah_ref = row[0]
                            question = row[1]

                            # Validate required fields
                            if not ayah_ref or not question:
                                raise ValueError("Missing required fields in first or second column")

                            surah, ayah = self._parse_ayah_reference(ayah_ref)
                            question = question.strip()

                            print(f"Processing surah {surah}, ayah {ayah}, question: {question}")

                            # Create a new workflow instance for each question
                            workflow = AnsariWorkflow(
                                self.settings, system_prompt_file=self.settings.AYAH_SYSTEM_PROMPT_FILE_NAME
                            )

                            ayah_id = surah * 1000 + ayah
                            workflow_steps = [
                                (
                                    "search",
                                    {
                                        "query": question,
                                        "tool_name": "search_tafsir",
                                        "metadata_filter": f"part.from_ayah_int<={ayah_id} AND part.to_ayah_int>={ayah_id}",
                                    },
                                ),
                            ]

                            if self.use_query_generation:
                                workflow_steps.append(("gen_query", {"input": question, "target_corpus": "tafsir"}))

                            workflow_steps.append(("gen_answer", {"input": question, "search_results_indices": [0]}))

                            # Execute the workflow
                            workflow_output = workflow.execute_workflow(workflow_steps)
                            # The answer is the last item in the workflow output
                            answer = workflow_output[-1]

                            # Add answer to row and write
                            row.append(answer)
                            writer.writerow(row)
                            output_file.flush()

                        except Exception as e:
                            logging.error(f"Error processing row: {e}")
                            row.append(f"ERROR: {str(e)}")
                            writer.writerow(row)
                            output_file.flush()
                            continue

            print(f"Results saved to {os.path.abspath(output_file_path)}")

        except Exception as e:
            logging.error(f"Error processing file: {e}")
            return
