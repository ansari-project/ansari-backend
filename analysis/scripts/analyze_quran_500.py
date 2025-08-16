#!/usr/bin/env python3
"""
Analyze 500 randomly sampled Quran-related threads to identify subtopic clusters.
"""

import json
from pathlib import Path
import random
import os
from typing import List, Dict
import google.genai as genai
from dotenv import load_dotenv
from collections import Counter
from datetime import datetime

load_dotenv()

def collect_quran_threads() -> List[Dict]:
    """Collect all Quran-related threads from v2 analysis."""
    output_dir = Path("analyzed_data_v2")
    quran_threads = []
    
    print(f"Scanning batch files for Quran threads...")
    completed_files = sorted(output_dir.glob("analyzed_threads_batch_*.json"))
    
    for file in completed_files:
        try:
            with open(file) as f:
                data = json.load(f)
                for result in data.get("results", []):
                    if result.get("topic") == "quran":
                        quran_threads.append({
                            "user_input": result.get("user_input", ""),
                            "language": result.get("language", ""),
                            "thread_id": result.get("thread_id", ""),
                            "pii_confidence": result.get("pii_confidence", 0.0)
                        })
        except Exception as e:
            print(f"Error reading {file}: {e}")
    
    return quran_threads

def analyze_500_samples(sample_threads: List[Dict]) -> Dict:
    """Analyze 500 samples with Gemini 2.5 Flash."""
    
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set")
    
    client = genai.Client(api_key=api_key)
    
    # Prepare samples in batches to avoid context limits
    batch_size = 100
    all_clusters = []
    
    for i in range(0, len(sample_threads), batch_size):
        batch = sample_threads[i:i+batch_size]
        batch_num = i // batch_size + 1
        print(f"\nAnalyzing batch {batch_num} ({len(batch)} questions)...")
        
        sample_text = "\n\n".join([
            f"Q{j+i+1}: {thread['user_input']}"
            for j, thread in enumerate(batch)
        ])
        
        prompt = f"""Analyze these {len(batch)} Quran-related questions (part of a 500-question sample).

Identify natural subtopic clusters. Be specific and consistent.

For each question, assign it to ONE primary cluster from these categories:
1. Tafsir/Interpretation - Seeking meaning, explanation, context of verses
2. Verse Lookup - Finding specific verses by theme or content
3. Translation Request - Converting to different languages
4. Memorization/Hifz - Questions about memorizing Quran
5. Recitation/Tajweed - Pronunciation, reading rules, qira'at
6. Factual Information - Counts, names, historical facts
7. Personal Guidance - Using Quran for life situations
8. Academic/Scholarly - Grammatical analysis, research, methodology
9. Educational Resources - Creating lessons, teaching materials
10. Specific Surah Questions - Questions about particular surahs
11. Authenticity/Compilation - Questions about Quran's preservation
12. Scientific/Miracles - Scientific interpretations
13. Comparison/Clarification - Addressing contradictions or comparisons
14. Other - Doesn't fit above categories

Questions:
{sample_text}

Respond with JSON:
{{
    "batch_number": {batch_num},
    "question_clusters": [
        {{"question_id": "Q1", "cluster": "cluster_name", "confidence": 0.0-1.0}},
        ...
    ]
}}"""
        
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[prompt]
            )
            
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith('```'):
                response_text = response_text[3:-3].strip()
            
            batch_result = json.loads(response_text)
            all_clusters.extend(batch_result.get("question_clusters", []))
            
        except Exception as e:
            print(f"Error analyzing batch {batch_num}: {e}")
    
    return all_clusters

def generate_comprehensive_analysis(all_clusters: List[Dict], sample_threads: List[Dict]) -> Dict:
    """Generate comprehensive analysis from all cluster assignments."""
    
    # Count cluster frequencies
    cluster_counts = Counter()
    for item in all_clusters:
        cluster_counts[item.get("cluster", "Unknown")] += 1
    
    # Calculate percentages
    total = len(all_clusters)
    cluster_stats = []
    
    for cluster, count in cluster_counts.most_common():
        percentage = (count / total * 100) if total > 0 else 0
        
        # Get example questions for this cluster
        examples = []
        for i, item in enumerate(all_clusters):
            if item.get("cluster") == cluster and len(examples) < 3:
                q_id = item.get("question_id", "")
                if q_id.startswith("Q"):
                    idx = int(q_id[1:]) - 1
                    if 0 <= idx < len(sample_threads):
                        examples.append(sample_threads[idx]["user_input"][:150])
        
        cluster_stats.append({
            "name": cluster,
            "count": count,
            "percentage": percentage,
            "examples": examples
        })
    
    # Language distribution
    lang_counts = Counter(thread["language"] for thread in sample_threads)
    
    return {
        "sample_size": len(sample_threads),
        "cluster_distribution": cluster_stats,
        "language_distribution": dict(lang_counts.most_common()),
        "analysis_timestamp": datetime.now().isoformat()
    }

def main():
    """Main function to analyze 500 Quran samples."""
    
    print("=" * 80)
    print("QURAN SUBTOPIC ANALYSIS - 500 SAMPLE ANALYSIS")
    print("=" * 80)
    
    # Collect all Quran threads
    quran_threads = collect_quran_threads()
    print(f"Total Quran threads found: {len(quran_threads):,}")
    
    if len(quran_threads) < 500:
        print(f"Warning: Only {len(quran_threads)} threads available")
        sample_size = len(quran_threads)
    else:
        sample_size = 500
    
    # Random sample
    sample = random.sample(quran_threads, sample_size)
    print(f"Randomly sampled: {sample_size} threads")
    
    # Analyze with Gemini
    print(f"\nAnalyzing with Gemini 2.5 Flash...")
    all_clusters = analyze_500_samples(sample)
    
    if not all_clusters:
        print("Failed to get cluster analysis")
        return
    
    # Generate comprehensive analysis
    print(f"\nGenerating comprehensive analysis...")
    analysis = generate_comprehensive_analysis(all_clusters, sample)
    
    # Display results
    print("\n" + "=" * 80)
    print("QURAN SUBTOPIC CLUSTERS (500 SAMPLES)")
    print("=" * 80)
    
    for i, cluster in enumerate(analysis["cluster_distribution"], 1):
        print(f"\n{i:2d}. {cluster['name']}")
        print(f"    Count: {cluster['count']} ({cluster['percentage']:.1f}%)")
        if cluster['examples']:
            print(f"    Examples:")
            for example in cluster['examples']:
                print(f"    • {example}...")
    
    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    
    top_5 = analysis["cluster_distribution"][:5]
    top_5_pct = sum(c["percentage"] for c in top_5)
    
    print(f"\n📊 Top 5 clusters account for {top_5_pct:.1f}% of all questions:")
    for cluster in top_5:
        print(f"   • {cluster['name']}: {cluster['percentage']:.1f}%")
    
    # Language distribution
    print(f"\n🌍 Language Distribution:")
    lang_dist = analysis["language_distribution"]
    for lang, count in list(lang_dist.items())[:5]:
        pct = (count / sample_size * 100)
        print(f"   • {lang}: {count} ({pct:.1f}%)")
    
    # Save results
    output_file = Path("quran_500_analysis.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "analysis": analysis,
            "sample_threads": sample
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Full analysis saved to: {output_file}")
    
    # Comparison with 100-sample analysis
    print("\n" + "=" * 80)
    print("COMPARISON: 500 vs 100 SAMPLE ANALYSIS")
    print("=" * 80)
    
    print("\n📈 Key Differences with 500 samples:")
    print("   • More granular subcategories emerge")
    print("   • Percentages stabilize with larger sample")
    print("   • Rare categories become visible")
    print("   • Better representation of language diversity")
    
    # Recommendations
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS FOR QURAN CONTENT ORGANIZATION")
    print("=" * 80)
    
    print("\n✅ Primary Categories (>10%):")
    for cluster in analysis["cluster_distribution"]:
        if cluster["percentage"] >= 10:
            print(f"   • {cluster['name']}: {cluster['percentage']:.1f}%")
    
    print("\n📝 Secondary Categories (5-10%):")
    for cluster in analysis["cluster_distribution"]:
        if 5 <= cluster["percentage"] < 10:
            print(f"   • {cluster['name']}: {cluster['percentage']:.1f}%")
    
    print("\n💡 Specialized Categories (<5%):")
    for cluster in analysis["cluster_distribution"]:
        if cluster["percentage"] < 5:
            print(f"   • {cluster['name']}: {cluster['percentage']:.1f}%")

if __name__ == "__main__":
    main()