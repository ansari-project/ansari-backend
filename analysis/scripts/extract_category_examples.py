#!/usr/bin/env python3
"""Extract examples of Islamic Life & Thought and Khutbah categories."""

import json
from pathlib import Path
import random

def extract_category_examples():
    """Extract examples of specific topic categories."""
    output_dir = Path("analyzed_data_v2")
    
    # Collect threads by category
    islamic_life_thought = []
    khutbah = []
    fiqh = []  # For comparison
    
    # Read all completed files
    completed_files = sorted(output_dir.glob("analyzed_threads_batch_*.json"))
    
    print(f"Scanning {len(completed_files)} batch files for category examples...\n")
    
    for file in completed_files:
        try:
            with open(file) as f:
                data = json.load(f)
                for result in data.get("results", []):
                    topic = result.get("topic", "")
                    
                    # Create entry with relevant info
                    entry = {
                        "user_input": result.get("user_input", ""),
                        "topic": topic,
                        "language": result.get("language", ""),
                        "reasoning": result.get("reasoning", ""),
                        "pii_confidence": result.get("pii_confidence", 0.0)
                    }
                    
                    # Categorize by topic
                    if topic == "Islamic Life & Thought":
                        islamic_life_thought.append(entry)
                    elif topic == "khutbah":
                        khutbah.append(entry)
                    elif topic == "fiqh":
                        fiqh.append(entry)
                        
        except Exception as e:
            print(f"Error reading {file}: {e}")
    
    # Print statistics
    print("=" * 80)
    print("CATEGORY DISTRIBUTION")
    print("=" * 80)
    print(f"Islamic Life & Thought: {len(islamic_life_thought):,}")
    print(f"Khutbah: {len(khutbah):,}")
    print(f"Fiqh (for comparison): {len(fiqh):,}")
    
    # Show examples of ISLAMIC LIFE & THOUGHT
    print("\n" + "=" * 80)
    print("EXAMPLES OF ISLAMIC LIFE & THOUGHT")
    print("=" * 80)
    print("\nThis category includes: Islamic philosophy, concepts, culture, lifestyle,")
    print("community discussions, contemporary commentary, motivational content")
    print("-" * 80)
    
    # Randomly sample to get diverse examples
    if islamic_life_thought:
        # Get a mix of different types
        samples = random.sample(islamic_life_thought, min(15, len(islamic_life_thought)))
        
        for i, entry in enumerate(samples[:15], 1):
            print(f"\n--- Example {i} ---")
            print(f"Language: {entry['language']}")
            input_text = entry['user_input']
            if len(input_text) > 300:
                input_text = input_text[:300] + "..."
            print(f"User Input: {input_text}")
            print(f"Reasoning: {entry['reasoning'][:200]}..." if len(entry['reasoning']) > 200 else f"Reasoning: {entry['reasoning']}")
    
    # Show examples of KHUTBAH
    print("\n" + "=" * 80)
    print("EXAMPLES OF KHUTBAH (SERMONS)")
    print("=" * 80)
    print("\nThis category includes: Sermons, Friday prayer speeches, khutbah content")
    print("-" * 80)
    
    if khutbah:
        # Show all khutbah examples (since there are fewer)
        for i, entry in enumerate(khutbah[:10], 1):
            print(f"\n--- Example {i} ---")
            print(f"Language: {entry['language']}")
            input_text = entry['user_input']
            if len(input_text) > 300:
                input_text = input_text[:300] + "..."
            print(f"User Input: {input_text}")
            print(f"Reasoning: {entry['reasoning'][:200]}..." if len(entry['reasoning']) > 200 else f"Reasoning: {entry['reasoning']}")
    else:
        print("\nNo khutbah examples found in current batch.")
    
    # Show some borderline cases between Islamic Life & Thought and Fiqh
    print("\n" + "=" * 80)
    print("COMPARISON: ISLAMIC LIFE & THOUGHT vs FIQH")
    print("=" * 80)
    print("\nShowing how the model distinguishes between these categories:")
    print("-" * 80)
    
    # Find examples that might be borderline
    life_examples = random.sample(islamic_life_thought, min(3, len(islamic_life_thought)))
    fiqh_examples = random.sample(fiqh, min(3, len(fiqh)))
    
    print("\n### Classified as Islamic Life & Thought (lifestyle/philosophy):")
    for i, entry in enumerate(life_examples, 1):
        print(f"\n{i}. {entry['user_input'][:150]}...")
        print(f"   → Reasoning: {entry['reasoning'][:150]}...")
    
    print("\n### Classified as Fiqh (jurisprudence/rulings):")
    for i, entry in enumerate(fiqh_examples, 1):
        print(f"\n{i}. {entry['user_input'][:150]}...")
        print(f"   → Reasoning: {entry['reasoning'][:150]}...")
    
    # Analyze patterns in Islamic Life & Thought
    print("\n" + "=" * 80)
    print("PATTERNS IN ISLAMIC LIFE & THOUGHT")
    print("=" * 80)
    
    # Look for common themes
    themes = {
        "marriage/relationships": [],
        "personal struggles": [],
        "philosophy/concepts": [],
        "culture/lifestyle": [],
        "motivation/inspiration": [],
        "community/social": [],
        "contemporary issues": []
    }
    
    for entry in islamic_life_thought[:100]:  # Sample first 100
        input_lower = entry['user_input'].lower()
        reasoning_lower = entry['reasoning'].lower()
        
        if any(word in input_lower for word in ["marriage", "husband", "wife", "spouse", "love", "relationship"]):
            themes["marriage/relationships"].append(entry)
        elif any(word in input_lower for word in ["struggle", "addiction", "depression", "anxiety", "problem"]):
            themes["personal struggles"].append(entry)
        elif any(word in input_lower for word in ["concept", "philosophy", "meaning", "understanding", "belief"]):
            themes["philosophy/concepts"].append(entry)
        elif any(word in input_lower for word in ["culture", "lifestyle", "living", "daily", "practice"]):
            themes["culture/lifestyle"].append(entry)
        elif any(word in input_lower for word in ["motivation", "inspiration", "hope", "strength"]):
            themes["motivation/inspiration"].append(entry)
        elif any(word in input_lower for word in ["community", "society", "muslim", "ummah"]):
            themes["community/social"].append(entry)
        elif any(word in input_lower for word in ["modern", "contemporary", "today", "current"]):
            themes["contemporary issues"].append(entry)
    
    print("\nCommon themes in Islamic Life & Thought:")
    for theme, entries in themes.items():
        if entries:
            print(f"  • {theme.replace('_', ' ').title()}: {len(entries)} examples")
    
    # Language distribution in each category
    print("\n" + "=" * 80)
    print("LANGUAGE DISTRIBUTION BY CATEGORY")
    print("=" * 80)
    
    def get_language_dist(entries):
        from collections import Counter
        langs = Counter(e['language'] for e in entries)
        return langs.most_common(5)
    
    print("\nIslamic Life & Thought - Top Languages:")
    for lang, count in get_language_dist(islamic_life_thought):
        pct = count / len(islamic_life_thought) * 100 if islamic_life_thought else 0
        print(f"  • {lang}: {count:,} ({pct:.1f}%)")
    
    if khutbah:
        print("\nKhutbah - Top Languages:")
        for lang, count in get_language_dist(khutbah):
            pct = count / len(khutbah) * 100 if khutbah else 0
            print(f"  • {lang}: {count:,} ({pct:.1f}%)")

if __name__ == "__main__":
    extract_category_examples()