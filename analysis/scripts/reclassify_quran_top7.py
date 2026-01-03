#!/usr/bin/env python3
"""
Reclassify all non-PII Quran questions into top 7 categories plus other.
"""

import json
from pathlib import Path
import os
import google.genai as genai
from dotenv import load_dotenv
from collections import Counter, defaultdict
import random
from datetime import datetime

load_dotenv()


def collect_quran_no_pii():
    """Collect all Quran threads with 0.0 PII confidence."""
    output_dir = Path("analyzed_data_v2")
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


def classify_batch(batch, batch_num, client):
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
8. Other - Doesn't fit the above categories (including recitation, memorization, scientific miracles, etc.)

Questions to classify:
{questions_text}

Respond with ONLY a JSON array of classifications:
[
    {{"question_num": 1, "category": "category name"}},
    {{"question_num": 2, "category": "category name"}},
    ...
]

Use EXACTLY the category names as listed above."""

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
            q_num = item.get("question_num", 0) - 1
            if 0 <= q_num < len(batch):
                result.append(
                    {
                        "question": batch[q_num]["user_input"],
                        "language": batch[q_num]["language"],
                        "category": item.get("category", "Other"),
                    }
                )

        return result

    except Exception as e:
        print(f"Error in batch {batch_num}: {e}")
        return []


def main():
    """Main function to reclassify Quran questions."""

    print("=" * 80)
    print("QURAN QUESTION RECLASSIFICATION - TOP 7 CATEGORIES")
    print("=" * 80)

    # Collect all non-PII Quran questions
    questions = collect_quran_no_pii()
    print(f"Found {len(questions):,} Quran questions with no PII")

    if not questions:
        print("No questions found!")
        return

    # Initialize Gemini client
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not set")
        return

    client = genai.Client(api_key=api_key)

    # Process in batches
    batch_size = 50
    all_classifications = []

    print(f"\nProcessing {len(questions)} questions in batches of {batch_size}...")

    for i in range(0, len(questions), batch_size):
        batch = questions[i : i + batch_size]
        batch_num = i // batch_size + 1

        if batch_num % 10 == 1:
            print(f"Processing batch {batch_num}/{(len(questions) - 1) // batch_size + 1}...")

        classified = classify_batch(batch, batch_num, client)
        all_classifications.extend(classified)

    print(f"\nSuccessfully classified {len(all_classifications):,} questions")

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

    total = len(all_classifications)

    for cat, count in category_counts:
        percentage = (count / total * 100) if total > 0 else 0
        print(f"\n{cat}")
        print(f"  Count: {count:,} ({percentage:.1f}%)")
        print("  Examples:")

        # Get 5 random examples
        examples = random.sample(category_data[cat], min(5, len(category_data[cat])))
        for j, example in enumerate(examples, 1):
            text = example["question"]
            if len(text) > 150:
                text = text[:150] + "..."
            print(f"    {j}. {text}")

    # Language distribution per category
    print("\n" + "=" * 80)
    print("LANGUAGE DISTRIBUTION BY CATEGORY")
    print("=" * 80)

    for cat, count in category_counts[:8]:  # Top 7 + Other
        items = category_data[cat]
        lang_counts = Counter(item["language"] for item in items)

        print(f"\n{cat}:")
        for lang, lcount in lang_counts.most_common(5):
            lpct = lcount / len(items) * 100
            print(f"  {lang}: {lcount:,} ({lpct:.1f}%)")

    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)

    top_7_total = sum(count for cat, count in category_counts[:7])
    top_7_pct = (top_7_total / total * 100) if total > 0 else 0

    print(f"\nTotal questions classified: {total:,}")
    print(f"Top 7 categories cover: {top_7_total:,} ({top_7_pct:.1f}%)")

    if "Other" in category_data:
        other_count = len(category_data["Other"])
        other_pct = (other_count / total * 100) if total > 0 else 0
        print(f"Other category: {other_count:,} ({other_pct:.1f}%)")

    # Save results
    output_file = Path("quran_top7_classification.json")

    save_data = {
        "total_questions": total,
        "classification_date": datetime.now().isoformat(),
        "categories": [
            {
                "name": cat,
                "count": count,
                "percentage": (count / total * 100) if total > 0 else 0,
                "examples": [
                    {"question": ex["question"][:500], "language": ex["language"]}
                    for ex in random.sample(category_data[cat], min(10, len(category_data[cat])))
                ],
            }
            for cat, count in category_counts
        ],
        "language_distribution": dict(Counter(item["language"] for item in all_classifications).most_common()),
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Full results saved to: {output_file}")

    # Final insights
    print("\n" + "=" * 80)
    print("KEY INSIGHTS")
    print("=" * 80)

    print("\n📊 Distribution Pattern:")
    if category_counts:
        if category_counts[0][1] / total > 0.25:
            print(f"  • Heavily dominated by {category_counts[0][0]} ({category_counts[0][1] / total * 100:.1f}%)")
        else:
            print("  • Well-distributed across categories")

    print("\n🎯 Implementation Recommendations:")
    print("  1. Prioritize Tafsir & Interpretation features")
    print("  2. Build robust verse search/lookup system")
    print("  3. Create factual information database")
    print("  4. Develop educational resource templates")
    print("  5. Add scholarly analysis tools")
    print("  6. Implement personal guidance pathways")
    print("  7. Integrate translation services")


if __name__ == "__main__":
    main()
