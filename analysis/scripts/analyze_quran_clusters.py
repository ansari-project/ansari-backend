#!/usr/bin/env python3
"""
Analyze Quran-related threads to identify natural subtopic clusters.
Uses random sampling and LLM analysis to discover patterns.
"""

import json
from pathlib import Path
import random
import os
from typing import List, Dict
import google.genai as genai
from dotenv import load_dotenv
from collections import Counter

load_dotenv()


def collect_quran_threads() -> List[Dict]:
    """Collect all Quran-related threads from v2 analysis."""
    output_dir = Path("analyzed_data_v2")
    quran_threads = []

    # Read all completed files
    completed_files = sorted(output_dir.glob("analyzed_threads_batch_*.json"))

    print(f"Scanning {len(completed_files)} batch files for Quran threads...")

    for file in completed_files:
        try:
            with open(file) as f:
                data = json.load(f)
                for result in data.get("results", []):
                    if result.get("topic") == "quran":
                        quran_threads.append(
                            {
                                "user_input": result.get("user_input", ""),
                                "language": result.get("language", ""),
                                "thread_id": result.get("thread_id", ""),
                            }
                        )
        except Exception as e:
            print(f"Error reading {file}: {e}")

    return quran_threads


def analyze_clusters_with_llm(sample_threads: List[Dict]) -> Dict:
    """Use LLM to identify natural clusters in Quran-related questions."""

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set")

    client = genai.Client(api_key=api_key)

    # Prepare the sample for analysis
    sample_text = "\n\n".join([f"Question {i + 1}: {thread['user_input']}" for i, thread in enumerate(sample_threads)])

    prompt = f"""Analyze these {len(sample_threads)} Quran-related questions and identify natural subtopic clusters.

For each question, assign it to ONE primary cluster. After reviewing all questions, provide:
1. A list of discovered clusters with clear definitions
2. The distribution of questions across clusters
3. Insights about user needs and patterns

Questions to analyze:
{sample_text}

Provide response in JSON format:
{{
    "clusters": [
        {{
            "name": "cluster_name",
            "description": "what this cluster represents",
            "question_indices": [list of question numbers in this cluster],
            "example_questions": [2-3 representative examples]
        }}
    ],
    "insights": {{
        "primary_user_needs": ["list of main needs"],
        "knowledge_gaps": ["areas where users need help"],
        "complexity_patterns": "observation about question complexity"
    }},
    "recommended_taxonomy": {{
        "main_categories": ["ordered list of main categories"],
        "subcategories": {{
            "category_name": ["list of subcategories"]
        }}
    }}
}}"""

    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=[prompt])

        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:-3].strip()
        elif response_text.startswith("```"):
            response_text = response_text[3:-3].strip()

        return json.loads(response_text)
    except Exception as e:
        print(f"Error analyzing with LLM: {e}")
        return None


def analyze_quran_subtopics():
    """Main function to analyze Quran subtopics."""

    # Collect all Quran threads
    print("=" * 80)
    print("QURAN SUBTOPIC ANALYSIS")
    print("=" * 80)

    quran_threads = collect_quran_threads()
    print(f"\nTotal Quran threads found: {len(quran_threads):,}")

    if not quran_threads:
        print("No Quran threads found!")
        return

    # Sample threads for analysis
    sample_size = min(100, len(quran_threads))
    sample = random.sample(quran_threads, sample_size)
    print(f"Randomly sampled: {sample_size} threads")

    # Analyze with LLM
    print("\nAnalyzing clusters with Gemini 2.5 Flash...")
    analysis = analyze_clusters_with_llm(sample)

    if not analysis:
        print("Failed to get LLM analysis")
        return

    # Display results
    print("\n" + "=" * 80)
    print("DISCOVERED QURAN SUBTOPIC CLUSTERS")
    print("=" * 80)

    clusters = analysis.get("clusters", [])

    # Sort clusters by size
    clusters_sorted = sorted(clusters, key=lambda x: len(x.get("question_indices", [])), reverse=True)

    for i, cluster in enumerate(clusters_sorted, 1):
        name = cluster.get("name", "Unknown")
        desc = cluster.get("description", "")
        count = len(cluster.get("question_indices", []))
        percentage = (count / sample_size) * 100

        print(f"\n{i}. {name.upper()}")
        print(f"   Description: {desc}")
        print(f"   Count: {count} ({percentage:.1f}%)")
        print("   Examples:")
        for example in cluster.get("example_questions", [])[:3]:
            if len(example) > 100:
                example = example[:100] + "..."
            print(f"   • {example}")

    # Display insights
    insights = analysis.get("insights", {})
    if insights:
        print("\n" + "=" * 80)
        print("KEY INSIGHTS")
        print("=" * 80)

        print("\n📊 Primary User Needs:")
        for need in insights.get("primary_user_needs", []):
            print(f"   • {need}")

        print("\n📚 Knowledge Gaps:")
        for gap in insights.get("knowledge_gaps", []):
            print(f"   • {gap}")

        print(f"\n💡 Complexity Pattern: {insights.get('complexity_patterns', 'N/A')}")

    # Display recommended taxonomy
    taxonomy = analysis.get("recommended_taxonomy", {})
    if taxonomy:
        print("\n" + "=" * 80)
        print("RECOMMENDED TAXONOMY FOR QURAN CONTENT")
        print("=" * 80)

        print("\n📋 Main Categories (in priority order):")
        for cat in taxonomy.get("main_categories", []):
            print(f"   1. {cat}")
            subcats = taxonomy.get("subcategories", {}).get(cat, [])
            if subcats:
                for subcat in subcats:
                    print(f"      • {subcat}")

    # Save full analysis
    output_file = Path("quran_cluster_analysis.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "sample_size": sample_size,
                "total_quran_threads": len(quran_threads),
                "analysis": analysis,
                "sample_threads": sample,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\n💾 Full analysis saved to: {output_file}")

    # Additional language analysis
    print("\n" + "=" * 80)
    print("LANGUAGE DISTRIBUTION IN QURAN QUESTIONS")
    print("=" * 80)

    lang_counter = Counter(thread["language"] for thread in quran_threads)
    for lang, count in lang_counter.most_common(10):
        percentage = (count / len(quran_threads)) * 100
        print(f"   {lang:15s}: {count:5,} ({percentage:5.1f}%)")

    # Sample of non-English Quran questions
    print("\n" + "=" * 80)
    print("SAMPLE NON-ENGLISH QURAN QUESTIONS")
    print("=" * 80)

    non_english = [t for t in quran_threads if t["language"] != "english"]
    if non_english:
        samples = random.sample(non_english, min(5, len(non_english)))
        for i, thread in enumerate(samples, 1):
            print(f"\n{i}. Language: {thread['language']}")
            text = thread["user_input"][:200] + "..." if len(thread["user_input"]) > 200 else thread["user_input"]
            print(f"   {text}")


if __name__ == "__main__":
    analyze_quran_subtopics()
