# Arabic Diacritic Stripping for Word Documents

## Overview

This Python script prepares Arabic text in Microsoft Word documents from "The Kuwaiti Encyclopaedia of Islamic Jurisprudence" for use with Vectara Arabic text embedding models. It does this by removing diacritics (tashkeel) from the text.  This preprocessing step is essential for optimal semantic indexing and search functionality with Vectara. 

## Why is this Important? 

Without removing diacritics, Vectara's Arabic text embedding models cannot accurately represent the core meaning of words. This severely hinders the effectiveness of semantic search within the text.

## Script Functionality

The script leverages the following libraries to achieve its task:

* **textract:** Extracts text content from Microsoft Word (.doc) files.
* **pyarabic.araby:** Provides tools for stripping diacritics from Arabic text.

## How to Use

**1. Install Dependencies**

Ensure you have the required libraries:

```bash
pip install PyArabic==0.6.15 textract==1.6.5 tqdm==4.66.1 
```

**2. Obtain the Source Documents**

* Download "The Kuwaiti Encyclopaedia of Islamic Jurisprudence" Word documents from [this link](https://content.awqaf.gov.kw/BasicPages/2020/9/4fcf6da511ff40cfa278d5873f5ff3ad.rar).
* Unrar the archive.
* Place the extracted Word documents in a dedicated directory.

**3. Configure the Script**

* Open the Python script.
* Update the `input_dir` variable with the full path to the directory containing the Word documents.

**4. Run the Script**

Execute the script from your terminal:

```bash
python strip_tashkeel.py
```

The script will process each Word document (.doc) in your specified directory and create a corresponding text file (.txt) with diacritics removed. The output files will be saved in a new folder called "txt" within the input directory.
