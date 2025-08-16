#!/usr/bin/env python3
"""
Extract all Quran questions with 0.0 PII confidence and save to a flat text file.
"""

import json
from pathlib import Path

def extract_quran_no_pii():
    """Extract all Quran threads with exactly 0.0 PII confidence."""
    output_dir = Path("analyzed_data_v2")
    quran_no_pii = []
    
    # Statistics
    total_quran = 0
    no_pii_count = 0
    
    print("Scanning batch files for Quran threads with 0.0 PII...")
    
    # Read all completed files
    completed_files = sorted(output_dir.glob("analyzed_threads_batch_*.json"))
    
    for file in completed_files:
        try:
            with open(file) as f:
                data = json.load(f)
                for result in data.get("results", []):
                    if result.get("topic") == "quran":
                        total_quran += 1
                        
                        # Check for exactly 0.0 PII confidence
                        if result.get("pii_confidence", 1.0) == 0.0:
                            user_input = result.get("user_input", "")
                            
                            # Replace actual newlines with \n string representation
                            user_input = user_input.replace('\n', '\\n')
                            user_input = user_input.replace('\r', '\\r')
                            
                            # Add to list
                            quran_no_pii.append(user_input)
                            no_pii_count += 1
                            
        except Exception as e:
            print(f"Error reading {file}: {e}")
    
    # Write to flat text file
    output_file = Path("quran_questions_no_pii.txt")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for question in quran_no_pii:
            f.write(question + '\n')
    
    # Print statistics
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"Total Quran threads: {total_quran:,}")
    print(f"Quran threads with 0.0 PII: {no_pii_count:,}")
    print(f"Percentage with no PII: {(no_pii_count/total_quran*100):.1f}%" if total_quran > 0 else "N/A")
    print(f"\nOutput saved to: {output_file}")
    print(f"File size: {output_file.stat().st_size:,} bytes" if output_file.exists() else "File not created")
    
    # Show sample of extracted questions
    print("\n" + "=" * 80)
    print("SAMPLE OF EXTRACTED QUESTIONS (first 10)")
    print("=" * 80)
    
    for i, question in enumerate(quran_no_pii[:10], 1):
        # For display, show first 150 chars
        display_text = question[:150] + "..." if len(question) > 150 else question
        print(f"\n{i}. {display_text}")
    
    return quran_no_pii

if __name__ == "__main__":
    questions = extract_quran_no_pii()
    print(f"\n✅ Successfully extracted {len(questions):,} Quran questions with no PII")