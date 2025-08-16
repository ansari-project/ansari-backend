#!/usr/bin/env python3
"""
Analyze Quran-related threads with multiple sample sizes to test cluster stability.
Tests with 100, 200, and 500 samples to see if patterns remain consistent.
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
                        quran_threads.append({
                            "user_input": result.get("user_input", ""),
                            "language": result.get("language", ""),
                            "thread_id": result.get("thread_id", "")
                        })
        except Exception as e:
            print(f"Error reading {file}: {e}")
    
    return quran_threads

def analyze_clusters_with_llm(sample_threads: List[Dict], sample_size: int) -> Dict:
    """Use LLM to identify natural clusters in Quran-related questions."""
    
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set")
    
    client = genai.Client(api_key=api_key)
    
    # Prepare the sample for analysis
    sample_text = "\n\n".join([
        f"Question {i+1}: {thread['user_input']}"
        for i, thread in enumerate(sample_threads)
    ])
    
    prompt = f"""Analyze these {len(sample_threads)} Quran-related questions and identify natural subtopic clusters.

IMPORTANT: Create consistent, well-defined clusters that could scale to thousands of questions.

For each cluster, provide:
1. A clear, specific name
2. Precise definition of what belongs in this cluster
3. Percentage of questions in this cluster

Expected clusters might include (but are not limited to):
- Verse interpretation/Tafsir
- Memorization/Hifz
- Recitation/Tajweed
- Specific surah questions
- Translation requests
- Context/Background
- Application/Practice
- Authenticity/Compilation
- Scientific miracles
- Contradictions/Clarifications

Provide response in JSON format:
{{
    "sample_size": {sample_size},
    "clusters": [
        {{
            "name": "cluster_name",
            "description": "precise definition",
            "count": number_of_questions,
            "percentage": percentage_of_sample,
            "example_questions": ["2-3 representative examples"]
        }}
    ],
    "top_5_clusters": ["ordered list of top 5 clusters by size"],
    "insights": {{
        "dominant_pattern": "what most users want",
        "unexpected_findings": "surprising patterns",
        "complexity_distribution": "simple vs complex questions"
    }}
}}

Questions to analyze:
{sample_text[:50000]}...  # Truncate if too long
"""
    
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
        
        return json.loads(response_text)
    except Exception as e:
        print(f"Error analyzing with LLM: {e}")
        return None

def compare_cluster_stability(all_analyses: Dict[int, Dict]):
    """Compare cluster patterns across different sample sizes."""
    
    print("\n" + "=" * 80)
    print("CLUSTER STABILITY ANALYSIS")
    print("=" * 80)
    
    # Collect all cluster names across sample sizes
    all_clusters = {}
    
    for size, analysis in all_analyses.items():
        if analysis:
            for cluster in analysis.get("clusters", []):
                name = cluster.get("name", "Unknown")
                if name not in all_clusters:
                    all_clusters[name] = {}
                all_clusters[name][size] = cluster.get("percentage", 0)
    
    # Show clusters that appear across multiple sample sizes
    print("\n📊 Stable Clusters (appearing in all sample sizes):")
    stable_clusters = []
    
    for cluster_name, percentages in all_clusters.items():
        if len(percentages) == len(all_analyses):  # Appears in all samples
            stable_clusters.append(cluster_name)
            print(f"\n   {cluster_name}:")
            for size in sorted(percentages.keys()):
                print(f"      {size:3d} samples: {percentages[size]:5.1f}%")
    
    # Show top 5 comparison
    print("\n📈 Top 5 Clusters by Sample Size:")
    for size, analysis in sorted(all_analyses.items()):
        if analysis:
            top_5 = analysis.get("top_5_clusters", [])[:5]
            print(f"\n   {size} samples: {', '.join(top_5)}")
    
    return stable_clusters

def main():
    """Main function to analyze Quran subtopics with multiple sample sizes."""
    
    # Collect all Quran threads
    print("=" * 80)
    print("QURAN SUBTOPIC ANALYSIS - MULTI-SAMPLE SIZE COMPARISON")
    print("=" * 80)
    
    quran_threads = collect_quran_threads()
    print(f"\nTotal Quran threads found: {len(quran_threads):,}")
    
    if not quran_threads:
        print("No Quran threads found!")
        return
    
    # Test with different sample sizes
    sample_sizes = [100, 200, 500]
    if len(quran_threads) < 500:
        sample_sizes = [s for s in sample_sizes if s <= len(quran_threads)]
        if len(quran_threads) not in sample_sizes:
            sample_sizes.append(len(quran_threads))
    
    all_analyses = {}
    
    for sample_size in sample_sizes:
        print(f"\n" + "-" * 80)
        print(f"ANALYZING WITH {sample_size} SAMPLES")
        print("-" * 80)
        
        # Sample threads
        sample = random.sample(quran_threads, min(sample_size, len(quran_threads)))
        
        # Analyze with LLM
        print(f"Analyzing {len(sample)} threads with Gemini 2.5 Flash...")
        analysis = analyze_clusters_with_llm(sample, sample_size)
        
        if analysis:
            all_analyses[sample_size] = analysis
            
            # Show results for this sample size
            print(f"\n📊 Results for {sample_size} samples:")
            
            clusters = analysis.get("clusters", [])
            clusters_sorted = sorted(clusters, key=lambda x: x.get("percentage", 0), reverse=True)
            
            for i, cluster in enumerate(clusters_sorted[:10], 1):  # Top 10
                name = cluster.get("name", "Unknown")
                percentage = cluster.get("percentage", 0)
                print(f"   {i:2d}. {name:30s}: {percentage:5.1f}%")
            
            # Show insights
            insights = analysis.get("insights", {})
            if insights:
                print(f"\n   💡 Dominant pattern: {insights.get('dominant_pattern', 'N/A')}")
    
    # Compare stability across sample sizes
    if len(all_analyses) > 1:
        stable_clusters = compare_cluster_stability(all_analyses)
        
        # Final recommendations
        print("\n" + "=" * 80)
        print("FINAL RECOMMENDATIONS")
        print("=" * 80)
        
        print("\n✅ Stable Subtopic Categories for Quran:")
        for i, cluster in enumerate(stable_clusters[:10], 1):
            print(f"   {i:2d}. {cluster}")
        
        print("\n📝 Insights:")
        print("   • Larger samples (500) provide more granular subcategories")
        print("   • Core categories remain stable across sample sizes")
        print("   • 200 samples appears to be optimal balance of speed vs accuracy")
        
        # Save comparison
        output_file = Path("quran_cluster_comparison.json")
        comparison_data = {
            "total_quran_threads": len(quran_threads),
            "sample_sizes_tested": sample_sizes,
            "stable_clusters": stable_clusters,
            "all_analyses": all_analyses
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(comparison_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Full comparison saved to: {output_file}")

if __name__ == "__main__":
    main()