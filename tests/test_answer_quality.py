import json
import logging
from logging import StreamHandler

import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader

from agents.ansari import Ansari

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

# Create a handler and set the logging level
console_handler = StreamHandler()
console_handler.setLevel(logging.INFO)

# Add the handler to the logger
LOGGER.addHandler(console_handler)


@pytest.fixture(scope="module")
def data():
    tenv = Environment(loader=FileSystemLoader("resources/templates/"))
    q_temp = tenv.get_template("ask_question.txt")
    df = pd.read_csv("evals/batik/batik-v1.csv")
    cache = {}
    return df, q_temp, cache


def answer_question(question, q_temp, cache):
    LOGGER.info(f'Answering question: {question["question"]}')
    options = [o.strip() for o in question["options"].split(",")]
    prompt = q_temp.render(question=question["question"], options=options)
    if prompt in cache.keys():
        LOGGER.info(f'Found {question["question"]} in cache')
        return cache[prompt]
    ansari = Ansari()
    result = "".join(filter(lambda x: x is not None, ansari.process_input(prompt)))
    LOGGER.info(f"Answer: {result}")
    cache[prompt] = result
    return result


def extract_prediction(row):
    raw = row["json_prediction"]
    raw = raw.replace("```", "")
    raw = raw.replace("json", "")
    raw = "{" + raw.split("{")[1]
    raw = raw.split("}")[0] + "}"
    raw = raw.strip()
    LOGGER.info(f"raw is: {raw}")
    raw_dict = json.loads(raw)
    return str(raw_dict["answer"])


def is_correct(row):
    clean_prediction = row["predicted"].strip().lower()
    clean_correct = row["correct"].replace("Ayah", "").strip().lower()
    return clean_correct == clean_prediction


def test_ansari_agent(data):
    df, q_temp, cache = data
    df["json_prediction"] = df.apply(
        lambda row: answer_question(row, q_temp, cache), axis=1
    )
    df["predicted"] = df.apply(extract_prediction, axis=1)
    df["correct_prediction"] = df.apply(is_correct, axis=1)
    correct_percentage = df["correct_prediction"].mean() * 100
    LOGGER.info(f"Percentage of correct predictions: {correct_percentage:.2f}%")

    wrong_predictions = df[df["correct_prediction"] == False]
    if not wrong_predictions.empty:
        LOGGER.info("\nQuestions with wrong predictions:")
        for index, row in wrong_predictions.iterrows():
            LOGGER.info(f"Question: {row['question']}")
            LOGGER.info(f"Correct Answer: {row['correct']}")
            LOGGER.info(f"Predicted Answer: {row['predicted']}")
            LOGGER.info("---------------------------------------")

    assert (
        correct_percentage >= 95
    ), f"Correct predictions percentage ({correct_percentage:.2f}%) is less than 95%"
