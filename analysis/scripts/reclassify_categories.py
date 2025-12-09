#!/usr/bin/env python3
"""
Reclassify categories with improved naming and consolidation:
1. Merge "halal and haram" into "fiqh"
2. Rename "general ideas" to "Islamic Life & Thought"
"""

import json
from pathlib import Path
from collections import Counter
from datetime import datetime


def reclassify_topics(topic):
    """Reclassify topics according to new schema."""
    # Merge halal and haram into fiqh
    if topic == "halal and haram":
        return "fiqh"
    # Rename general ideas to Islamic Life & Thought
    elif topic == "general ideas":
        return "Islamic Life & Thought"
    # Keep everything else the same
    else:
        return topic


def process_reclassification():
    """Process all analyzed files and generate new statistics."""
    analyzed_dir = Path("analyzed_data")

    # Collect all results with reclassification
    all_results = []
    total_threads = 0
    total_analyzed = 0
    batch_files_processed = 0

    print("Loading and reclassifying all analyzed batch files...")

    for batch_file in sorted(analyzed_dir.glob("analyzed_threads_batch_[0-9][0-9][0-9][0-9].json")):
        with open(batch_file) as f:
            data = json.load(f)

        batch_files_processed += 1
        total_threads += data.get("total_threads", 0)

        # Reclassify each result
        for result in data.get("results", []):
            # Apply reclassification
            original_topic = result.get("topic", "unknown")
            result["original_topic"] = original_topic
            result["topic"] = reclassify_topics(original_topic)
            all_results.append(result)

        total_analyzed += len(data.get("results", []))

        if batch_files_processed % 10 == 0:
            print(f"  Processed {batch_files_processed} batch files...")

    print(f"\nLoaded and reclassified {len(all_results)} analyzed threads from {batch_files_processed} batch files")

    # Analyze reclassified results
    languages = Counter()
    topics = Counter()
    original_topics = Counter()
    confidence_levels = Counter()
    pii_count = 0
    error_count = 0

    for result in all_results:
        lang = result.get("language", "unknown")
        topic = result.get("topic", "unknown")
        original_topic = result.get("original_topic", "unknown")
        confidence = result.get("confidence", "unknown")

        # Handle edge cases
        if isinstance(lang, list):
            lang = str(lang)
        if isinstance(topic, list):
            topic = str(topic)

        languages[str(lang)] += 1
        topics[str(topic)] += 1
        original_topics[str(original_topic)] += 1
        confidence_levels[str(confidence)] += 1

        if result.get("has_pii", False):
            pii_count += 1

        if lang == "error" or topic == "error":
            error_count += 1

    # Calculate success rate
    success_rate = ((total_analyzed - error_count) / total_analyzed * 100) if total_analyzed > 0 else 0

    # Create comprehensive summary with new categories
    summary = {
        "reclassification_date": datetime.now().isoformat(),
        "reclassification_rules": {
            "halal and haram": "merged into fiqh",
            "general ideas": "renamed to Islamic Life & Thought",
        },
        "data_collection": {
            "total_batch_files": batch_files_processed,
            "total_threads_in_dataset": total_threads,
            "threads_with_user_messages": total_analyzed,
            "threads_without_user_messages": total_threads - total_analyzed,
            "analyzable_threads_coverage": "100.00%",
            "success_rate_percentage": round(success_rate, 2),
        },
        "language_analysis": {
            "total_languages_detected": len(languages),
            "distribution": dict(languages.most_common()),
            "top_languages": dict(languages.most_common(10)),
        },
        "topic_analysis_new": {"total_topics_identified": len(topics), "distribution": dict(topics.most_common())},
        "topic_analysis_original": {
            "total_topics_identified": len(original_topics),
            "distribution": dict(original_topics.most_common()),
        },
        "privacy_analysis": {
            "threads_with_pii": pii_count,
            "pii_percentage": round((pii_count / total_analyzed * 100), 2) if total_analyzed > 0 else 0,
        },
        "quality_metrics": {
            "confidence_distribution": dict(confidence_levels.most_common()),
            "error_count": error_count,
            "error_percentage": round((error_count / total_analyzed * 100), 2) if total_analyzed > 0 else 0,
        },
    }

    # Save reclassified summary
    output_file = "reclassified_analysis_summary.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Print detailed summary
    print("\n" + "=" * 100)
    print("RECLASSIFIED ANALYSIS SUMMARY")
    print("=" * 100)

    print("\n📊 DATA COLLECTION SUMMARY:")
    print(f"   Total batch files processed: {batch_files_processed}")
    print(f"   Total threads in dataset: {total_threads:,}")
    print(f"   Threads with user messages: {total_analyzed:,}")
    print(f"   Threads without user messages: {total_threads - total_analyzed:,}")
    print("   Analyzable threads coverage: 100.00%")
    print(f"   Success rate: {success_rate:.2f}%")

    print("\n🌍 LANGUAGE ANALYSIS (unchanged):")
    print(f"   Languages detected: {len(languages)}")
    for lang, count in languages.most_common(10):
        percentage = count / total_analyzed * 100
        print(f"   {lang:15s}: {count:7,} ({percentage:5.1f}%)")

    print("\n📚 NEW TOPIC DISTRIBUTION (with consolidation):")
    print(f"   Topics identified: {len(topics)}")
    for topic, count in topics.most_common():
        percentage = count / total_analyzed * 100
        print(f"   {topic:30s}: {count:7,} ({percentage:5.1f}%)")

    print("\n📚 ORIGINAL TOPIC DISTRIBUTION (for comparison):")
    print(f"   Topics identified: {len(original_topics)}")
    for topic, count in original_topics.most_common():
        percentage = count / total_analyzed * 100
        print(f"   {topic:30s}: {count:7,} ({percentage:5.1f}%)")

    # Calculate the change
    fiqh_original = original_topics.get("fiqh", 0)
    halal_haram_original = original_topics.get("halal and haram", 0)
    fiqh_new = topics.get("fiqh", 0)
    general_original = original_topics.get("general ideas", 0)
    life_thought_new = topics.get("Islamic Life & Thought", 0)

    print("\n🔄 RECLASSIFICATION IMPACT:")
    print(f"   Fiqh (original): {fiqh_original:,} ({fiqh_original / total_analyzed * 100:.1f}%)")
    print(f"   Halal and Haram (original): {halal_haram_original:,} ({halal_haram_original / total_analyzed * 100:.1f}%)")
    print(f"   → Fiqh (consolidated): {fiqh_new:,} ({fiqh_new / total_analyzed * 100:.1f}%)")
    print("   ")
    print(f"   General Ideas (original): {general_original:,} ({general_original / total_analyzed * 100:.1f}%)")
    print(f"   → Islamic Life & Thought (renamed): {life_thought_new:,} ({life_thought_new / total_analyzed * 100:.1f}%)")

    print("\n🔒 PRIVACY ANALYSIS (unchanged):")
    print(f"   Threads with PII: {pii_count:,} ({pii_count / total_analyzed * 100:.2f}%)")
    print(
        f"   Threads without PII: {total_analyzed - pii_count:,} ({(total_analyzed - pii_count) / total_analyzed * 100:.2f}%)"
    )

    print("\n⚙️  PROCESSING QUALITY (unchanged):")
    print(f"   Error count: {error_count:,} ({error_count / total_analyzed * 100:.2f}%)")
    successful = total_analyzed - error_count
    successful_pct = successful / total_analyzed * 100
    print(f"   Successful analyses: {successful:,} ({successful_pct:.2f}%)")

    print(f"\n💾 Summary saved to: {output_file}")
    print("=" * 100)

    return summary


if __name__ == "__main__":
    process_reclassification()
