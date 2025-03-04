import json

import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader

from ansari.agents import Ansari
from ansari.ansari_logger import get_logger
from ansari.config import get_settings

logger = get_logger()


@pytest.fixture(scope="module")
def data():
    tenv = Environment(loader=FileSystemLoader("src/ansari/resources/templates/"))
    # NOTE (optional): the content inside the `ask_question.txt` is written in the Jinja2 template language
    #   Refer to this for details: https://www.packetcoders.io/an-introduction-to-jinja2-for-network-automation/
    q_temp = tenv.get_template("ask_question.txt")
    df = pd.read_csv("tests/batik-v1-en.csv")
    cache = {}
    return df, q_temp, cache


def answer_question(question, q_temp, cache):
    logger.info(f"Answering question: {question['question']}")
    options = [o.strip() for o in question["options"].split(",")]
    prompt = q_temp.render(question=question["question"], options=options)
    if prompt in cache.keys():
        logger.info(f"Found {question['question']} in cache")
        return cache[prompt]
    ansari = Ansari(get_settings())
    result = "".join(filter(lambda x: x is not None, ansari.process_input(prompt)))
    logger.info(f"Answer: {result}")
    cache[prompt] = result
    return result


def extract_prediction(row):
    try:
        raw = row["json_prediction"]
        raw = raw.replace("```", "")
        raw = raw.replace("json", "")
        raw = "{" + raw.split("{")[1]
        raw = raw.split("}")[0] + "}"
        raw = raw.strip()
        logger.info(f"raw is: {raw}")
        raw_dict = json.loads(raw)
        return str(raw_dict["answer"])
    except IndexError:
        return "OUTPUT_PARSE_ERROR"


def is_correct(row):
    clean_prediction = row["predicted"].strip().lower()
    clean_correct = row["correct"].replace("Ayah", "").strip().lower()
    return clean_correct == clean_prediction


def test_ansari_agent(data):
    df, q_temp, cache = data
    df = df.sample(10)
    # For cost and efficiency reasons, we will only test 10 questions
    df["json_prediction"] = df.apply(
        lambda row: answer_question(row, q_temp, cache),
        axis=1,
    )
    df["predicted"] = df.apply(extract_prediction, axis=1)
    df["correct_prediction"] = df.apply(is_correct, axis=1)
    correct_percentage = df["correct_prediction"].mean() * 100
    logger.info(f"Percentage of correct predictions: {correct_percentage:.2f}%")

    wrong_predictions = df[~df["correct_prediction"]]
    if not wrong_predictions.empty:
        logger.info("\nQuestions with wrong predictions:")
        for index, row in wrong_predictions.iterrows():
            logger.info(f"Question: {row['question']}")
            logger.info(f"Correct Answer: {row['correct']}")
            logger.info(f"Predicted Answer: {row['predicted']}")
            logger.info("---------------------------------------")

    assert correct_percentage >= 80, f"Correct predictions percentage ({correct_percentage:.2f}%) is less than 95%"
