#!/usr/bin/env python3
"""
Reclassify a sample of non-PII Quran questions into top 7 categories for quick results.
"""

import json
from pathlib import Path
import os
import google.genai as genai
from dotenv import load_dotenv
from collections import defaultdict
import random
from datetime import datetime

load_dotenv()


def collect_quran_no_pii():
    """Collect all Quran threads with 0.0 PII confidence."""
    output_dir = Path("analysis/data-local/analyzed_data_v2")
    quran_no_pii = []

    print("Collecting Quran threads with 0.0 PII...")

    completed_files = sorted(output_dir.glob("analyzed_threads_batch_*.json"))

    for file in completed_files:
        try:
            with open(file) as f:
                data = json.load(f)
                for result in data.get("results", []):
                    if result.get("topic") == "quran" and result.get("pii_confidence", 1.0) == 0.0:
                        quran_no_pii.append(
                            {
                                "user_input": result.get("user_input", ""),
                                "language": result.get("language", ""),
                                "thread_id": result.get("thread_id", ""),
                            }
                        )
        except Exception as e:
            print(f"Error reading {file}: {e}")

    return quran_no_pii


def classify_batch(batch, client):
    """Classify a batch of questions into top 7 categories."""

    # Create numbered list for the batch
    questions_text = "\n".join([f"{i + 1}. {q['user_input'][:200]}" for i, q in enumerate(batch)])

    prompt = f"""Classify each Quran question into EXACTLY ONE of these 8 categories:

1. Tafsir & Interpretation - Seeking meaning, explanation, context, lessons from verses/surahs
2. Verse Finding & Lookup - Finding specific verses by theme, topic, or content
3. Factual Information - Counts, names, dates, historical facts about Quran
4. Educational Resources - Creating lessons, quizzes, teaching materials, study guides
5. Academic/Scholarly - Grammatical analysis, research, methodology, linguistic study
6. Personal Guidance - Using Quran for life situations, emotional support, spiritual guidance
7. Translation Services - Requesting translation or transliteration to different languages
8. Other - Doesn't fit above (recitation, memorization, scientific miracles, etc.)

Questions:
{questions_text}

Respond with ONLY a JSON array:
[{{"num": 1, "cat": "category name"}}, ...]

Use EXACT category names above."""

    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=[prompt])

        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:-3].strip()
        elif response_text.startswith("```"):
            response_text = response_text[3:-3].strip()

        classifications = json.loads(response_text)

        # Map classifications back to questions
        result = []
        for item in classifications:
            q_num = item.get("num", 0) - 1
            if 0 <= q_num < len(batch):
                result.append(
                    {
                        "question": batch[q_num]["user_input"],
                        "language": batch[q_num]["language"],
                        "category": item.get("cat", "Other"),
                    }
                )

        return result

    except Exception as e:
        print(f"Error classifying: {e}")
        return []


def main():
    """Main function to reclassify a sample of Quran questions."""

    print("=" * 80)
    print("QURAN QUESTION CLASSIFICATION - TOP 7 CATEGORIES (SAMPLE)")
    print("=" * 80)

    # Collect all non-PII Quran questions
    questions = collect_quran_no_pii()
    total_questions = len(questions)
    print(f"Found {total_questions:,} Quran questions with no PII")

    # Sample 300 for quick results
    sample_size = min(300, total_questions)
    sample = random.sample(questions, sample_size)
    print(f"Using sample of {sample_size} questions for analysis")

    # Initialize Gemini client
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not set")
        return

    client = genai.Client(api_key=api_key)

    # Process in batches
    batch_size = 20
    all_classifications = []

    print(f"\nProcessing {sample_size} questions in batches of {batch_size}...")

    for i in range(0, len(sample), batch_size):
        batch = sample[i : i + batch_size]
        batch_num = i // batch_size + 1
        print(f"  Batch {batch_num}/{(sample_size - 1) // batch_size + 1}...")

        classified = classify_batch(batch, client)
        all_classifications.extend(classified)

    print(f"\nSuccessfully classified {len(all_classifications)} questions")

    # Analyze results
    category_data = defaultdict(list)

    for item in all_classifications:
        category = item["category"]
        category_data[category].append(item)

    # Sort categories by count
    category_counts = [(cat, len(items)) for cat, items in category_data.items()]
    category_counts.sort(key=lambda x: x[1], reverse=True)

    # Display results
    print("\n" + "=" * 80)
    print("CLASSIFICATION RESULTS")
    print("=" * 80)

    classified_total = len(all_classifications)

    for cat, count in category_counts:
        percentage = (count / classified_total * 100) if classified_total > 0 else 0
        estimated_total = int(count / classified_total * total_questions)

        print(f"\n{cat}")
        print(f"  Sample: {count}/{classified_total} ({percentage:.1f}%)")
        print(f"  Estimated total: ~{estimated_total:,} of {total_questions:,}")
        print("  Examples:")

        # Get 5 random examples
        examples = random.sample(category_data[cat], min(5, len(category_data[cat])))
        for j, example in enumerate(examples, 1):
            text = example["question"]
            if len(text) > 120:
                text = text[:120] + "..."
            print(f"    {j}. {text}")

    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print(f"\nBased on {sample_size} sample from {total_questions:,} total questions:")

    top_3 = category_counts[:3]
    top_3_pct = sum(count for _, count in top_3) / classified_total * 100
    print(f"\nTop 3 categories cover {top_3_pct:.1f}% of questions:")
    for cat, count in top_3:
        pct = count / classified_total * 100
        print(f"  • {cat}: {pct:.1f}%")

    # Save results
    output_file = Path("analysis/data-local/quran_classification_sample.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    save_data = {
        "sample_size": sample_size,
        "total_questions": total_questions,
        "classification_date": datetime.now().isoformat(),
        "categories": [
            {
                "name": cat,
                "sample_count": count,
                "sample_percentage": (count / classified_total * 100),
                "estimated_total": int(count / classified_total * total_questions),
                "examples": [
                    ex["question"][:200] for ex in random.sample(category_data[cat], min(5, len(category_data[cat])))
                ],
            }
            for cat, count in category_counts
        ],
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Results saved to: {output_file}")


if __name__ == "__main__":
    main()
