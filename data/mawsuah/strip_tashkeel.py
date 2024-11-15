from pathlib import Path, PurePath

import textract
from pyarabic import araby
from tqdm.auto import tqdm

from ansari.ansari_logger import get_logger

logger = get_logger(__name__)


def strip_tashkeel_from_doc(input_file, output_file):
    text = textract.process(input_file).decode("utf-8")  # Extract text from .doc file

    stripped_text = araby.strip_diacritics(text)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(stripped_text)


input_dir = Path("/path/to/The Kuwaiti Encyclopaedia of Islamic Jurisprudence/word")
path_components = list(input_dir.parts)
path_components[-1] = "txt"
output_dir = PurePath(
    *path_components,
)  # --> "/path/to/The Kuwaiti Encyclopaedia of Islamic Jurisprudence/txt"

# iterate over all files in the directory
for input_file in tqdm(input_dir.glob("*.doc")):
    if input_file.is_file() and input_file.suffix == ".doc":
        logger.info(f"Processing {input_file.name}...")
        strip_tashkeel_from_doc(
            input_file,
            output_dir.joinpath(input_file.with_suffix(".txt").name),
        )
        logger.info(f"Done processing {input_file.name}")
