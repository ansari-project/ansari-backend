#!/usr/bin/env python3
"""Extract examples of threads with different PII confidence levels."""

import json
from pathlib import Path
import random

def extract_pii_examples():
    """Extract examples of different PII confidence levels."""
    output_dir = Path("analyzed_data_v2")
    
    # Collect threads by PII category
    definite_pii = []  # >= 0.9
    high_pii = []      # 0.7 - 0.9
    medium_pii = []    # 0.3 - 0.7
    low_pii = []       # 0.1 - 0.3
    very_low_pii = []  # 0.01 - 0.1
    no_pii = []        # 0.0
    
    # Read all completed files
    completed_files = sorted(output_dir.glob("analyzed_threads_batch_*.json"))
    
    print(f"Scanning {len(completed_files)} batch files for PII examples...\n")
    
    for file in completed_files:
        try:
            with open(file) as f:
                data = json.load(f)
                for result in data.get("results", []):
                    pii_conf = result.get("pii_confidence", 0.0)
                    
                    # Create entry with relevant info
                    entry = {
                        "pii_confidence": pii_conf,
                        "user_input": result.get("user_input", ""),
                        "reasoning": result.get("reasoning", ""),
                        "topic": result.get("topic", ""),
                        "language": result.get("language", ""),
                        "thread_id": result.get("thread_id", "")
                    }
                    
                    # Categorize by PII level
                    if pii_conf >= 0.9:
                        definite_pii.append(entry)
                    elif pii_conf >= 0.7:
                        high_pii.append(entry)
                    elif pii_conf >= 0.3:
                        medium_pii.append(entry)
                    elif pii_conf >= 0.1:
                        low_pii.append(entry)
                    elif pii_conf > 0.0:
                        very_low_pii.append(entry)
                    else:
                        no_pii.append(entry)
                        
        except Exception as e:
            print(f"Error reading {file}: {e}")
    
    # Print statistics
    print("=" * 80)
    print("PII CONFIDENCE DISTRIBUTION")
    print("=" * 80)
    print(f"Definite PII (≥0.9): {len(definite_pii)}")
    print(f"High PII (0.7-0.9): {len(high_pii)}")
    print(f"Medium PII (0.3-0.7): {len(medium_pii)}")
    print(f"Low PII (0.1-0.3): {len(low_pii)}")
    print(f"Very Low PII (0.01-0.1): {len(very_low_pii)}")
    print(f"No PII (0.0): {len(no_pii)}")
    
    # Show examples of DEFINITE PII (≥0.9)
    print("\n" + "=" * 80)
    print("EXAMPLES OF DEFINITE PII (confidence ≥ 0.9)")
    print("=" * 80)
    
    # Sort by confidence and show top examples
    definite_pii.sort(key=lambda x: x['pii_confidence'], reverse=True)
    
    for i, entry in enumerate(definite_pii[:5], 1):
        print(f"\n--- Example {i} ---")
        print(f"PII Confidence: {entry['pii_confidence']}")
        print(f"Topic: {entry['topic']}")
        print(f"Language: {entry['language']}")
        print(f"User Input: {entry['user_input'][:200]}..." if len(entry['user_input']) > 200 else f"User Input: {entry['user_input']}")
        print(f"Reasoning: {entry['reasoning']}")
    
    # Show examples of MEDIUM PII (0.3-0.7)
    print("\n" + "=" * 80)
    print("EXAMPLES OF MEDIUM PII (confidence 0.3-0.7)")
    print("=" * 80)
    
    # Sort by confidence and show examples from different confidence levels
    medium_pii.sort(key=lambda x: x['pii_confidence'], reverse=True)
    
    # Get examples from different parts of the medium range
    medium_examples = []
    if medium_pii:
        # High-medium (0.5-0.7)
        high_medium = [e for e in medium_pii if 0.5 <= e['pii_confidence'] < 0.7]
        if high_medium:
            medium_examples.extend(high_medium[:2])
        
        # Mid-medium (0.4-0.5)
        mid_medium = [e for e in medium_pii if 0.4 <= e['pii_confidence'] < 0.5]
        if mid_medium:
            medium_examples.extend(mid_medium[:2])
        
        # Low-medium (0.3-0.4)
        low_medium = [e for e in medium_pii if 0.3 <= e['pii_confidence'] < 0.4]
        if low_medium:
            medium_examples.extend(low_medium[:1])
    
    for i, entry in enumerate(medium_examples, 1):
        print(f"\n--- Example {i} ---")
        print(f"PII Confidence: {entry['pii_confidence']}")
        print(f"Topic: {entry['topic']}")
        print(f"Language: {entry['language']}")
        print(f"User Input: {entry['user_input'][:200]}..." if len(entry['user_input']) > 200 else f"User Input: {entry['user_input']}")
        print(f"Reasoning: {entry['reasoning']}")
    
    # Show examples of HIGH PII (0.7-0.9) for comparison
    print("\n" + "=" * 80)
    print("EXAMPLES OF HIGH PII (confidence 0.7-0.9)")
    print("=" * 80)
    
    high_pii.sort(key=lambda x: x['pii_confidence'], reverse=True)
    
    for i, entry in enumerate(high_pii[:3], 1):
        print(f"\n--- Example {i} ---")
        print(f"PII Confidence: {entry['pii_confidence']}")
        print(f"Topic: {entry['topic']}")
        print(f"Language: {entry['language']}")
        print(f"User Input: {entry['user_input'][:200]}..." if len(entry['user_input']) > 200 else f"User Input: {entry['user_input']}")
        print(f"Reasoning: {entry['reasoning']}")
    
    # Show examples of LOW PII (0.1-0.3) for comparison
    print("\n" + "=" * 80)
    print("EXAMPLES OF LOW PII (confidence 0.1-0.3)")
    print("=" * 80)
    
    # Get a mix of different confidence levels
    low_examples = []
    if low_pii:
        # 0.2 scores (most common)
        score_02 = [e for e in low_pii if 0.19 <= e['pii_confidence'] <= 0.21]
        if score_02:
            low_examples.extend(random.sample(score_02, min(3, len(score_02))))
        
        # 0.1 scores
        score_01 = [e for e in low_pii if 0.09 <= e['pii_confidence'] <= 0.11]
        if score_01:
            low_examples.extend(random.sample(score_01, min(2, len(score_01))))
    
    for i, entry in enumerate(low_examples[:5], 1):
        print(f"\n--- Example {i} ---")
        print(f"PII Confidence: {entry['pii_confidence']}")
        print(f"Topic: {entry['topic']}")
        print(f"Language: {entry['language']}")
        print(f"User Input: {entry['user_input'][:200]}..." if len(entry['user_input']) > 200 else f"User Input: {entry['user_input']}")
        print(f"Reasoning: {entry['reasoning']}")
    
    # Summary insights
    print("\n" + "=" * 80)
    print("KEY INSIGHTS")
    print("=" * 80)
    
    if definite_pii:
        print("\n📍 Definite PII patterns:")
        print("  - Full names often mentioned")
        print("  - Specific personal situations with identifiable details")
        print("  - Location information combined with personal details")
    
    if medium_pii:
        print("\n📍 Medium PII patterns:")
        print("  - Personal situations described without full names")
        print("  - General location references (cities, countries)")
        print("  - Family situations with some specifics")
    
    if low_pii:
        print("\n📍 Low PII patterns:")
        print("  - Generic personal contexts ('my husband', 'my family')")
        print("  - Common situations without unique identifiers")
        print("  - Age or gender mentioned without other details")

if __name__ == "__main__":
    extract_pii_examples()