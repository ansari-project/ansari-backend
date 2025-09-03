#!/usr/bin/env python3
"""Generate text-based histogram of PII confidence scores from v2 analysis."""

import json
from pathlib import Path
from collections import Counter
import statistics

def create_text_histogram(scores, bins=20, width=60):
    """Create a text-based histogram."""
    if not scores:
        return
    
    min_val = min(scores)
    max_val = max(scores)
    bin_width = (max_val - min_val) / bins if max_val > min_val else 1
    
    # Create bins
    histogram = {}
    for i in range(bins):
        bin_start = min_val + i * bin_width
        bin_end = min_val + (i + 1) * bin_width
        if i == bins - 1:  # Last bin includes max value
            bin_end = max_val + 0.001
        
        count = sum(1 for s in scores if bin_start <= s < bin_end)
        histogram[f"{bin_start:.2f}-{bin_end:.2f}"] = count
    
    # Find max count for scaling
    max_count = max(histogram.values()) if histogram else 1
    
    # Print histogram
    print("\n📊 PII Confidence Score Histogram:")
    print("=" * 80)
    
    for bin_range, count in histogram.items():
        bar_length = int((count / max_count) * width) if max_count > 0 else 0
        bar = '█' * bar_length
        pct = (count / len(scores)) * 100 if scores else 0
        print(f"{bin_range:12s} | {bar:<{width}} {count:6,} ({pct:5.1f}%)")
    
    print("=" * 80)

def analyze_pii_scores():
    """Analyze PII confidence scores and create histogram."""
    output_dir = Path("analyzed_data_v2")
    
    # Collect all PII scores
    pii_scores = []
    file_count = 0
    
    # Read all completed files
    completed_files = sorted(output_dir.glob("analyzed_threads_batch_*.json"))
    
    print(f"Found {len(completed_files)} completed batch files")
    
    for file in completed_files:
        try:
            with open(file) as f:
                data = json.load(f)
                file_count += 1
                for result in data.get("results", []):
                    pii_scores.append(result.get("pii_confidence", 0.0))
        except Exception as e:
            print(f"Error reading {file}: {e}")
    
    print(f"Successfully read {file_count} files")
    print(f"Total PII scores collected: {len(pii_scores):,}")
    
    if not pii_scores:
        print("No PII scores found!")
        return
    
    # Calculate statistics
    print("\n📊 PII Confidence Statistics:")
    print(f"  Count: {len(pii_scores):,}")
    print(f"  Mean: {statistics.mean(pii_scores):.4f}")
    print(f"  Median: {statistics.median(pii_scores):.4f}")
    print(f"  Std Dev: {statistics.stdev(pii_scores):.4f}" if len(pii_scores) > 1 else "  Std Dev: N/A")
    print(f"  Min: {min(pii_scores):.4f}")
    print(f"  Max: {max(pii_scores):.4f}")
    
    # Percentiles
    sorted_scores = sorted(pii_scores)
    percentiles = [10, 25, 50, 75, 90, 95, 99]
    print("\n📈 Percentiles:")
    for p in percentiles:
        idx = int(len(sorted_scores) * p / 100)
        idx = min(idx, len(sorted_scores) - 1)
        print(f"  {p:2d}th percentile: {sorted_scores[idx]:.4f}")
    
    # Categorize PII scores
    categories = [
        (0.0, 0.0, "No PII (0.0)"),
        (0.001, 0.1, "Very Low (0.001-0.1)"),
        (0.1, 0.3, "Low (0.1-0.3)"),
        (0.3, 0.6, "Medium (0.3-0.6)"),
        (0.6, 0.9, "High (0.6-0.9)"),
        (0.9, 1.0, "Definite (0.9-1.0)"),
    ]
    
    print("\n🔒 PII Risk Categories:")
    print("=" * 80)
    
    for min_val, max_val, label in categories:
        if min_val == 0.0 and max_val == 0.0:
            count = sum(1 for s in pii_scores if s == 0.0)
        else:
            count = sum(1 for s in pii_scores if min_val <= s <= max_val)
        
        pct = (count / len(pii_scores)) * 100
        bar = '█' * int(pct / 2)  # Visual bar (50% = full width)
        print(f"{label:25s}: {count:6,} ({pct:5.1f}%) {bar}")
    
    print("=" * 80)
    
    # Create main histogram
    create_text_histogram(pii_scores, bins=20)
    
    # Detailed breakdown for specific ranges
    print("\n📊 Detailed Score Distribution (0.05 intervals):")
    print("=" * 80)
    
    ranges = []
    for i in range(0, 20):  # 0.0 to 1.0 in 0.05 steps
        start = i * 0.05
        end = (i + 1) * 0.05
        ranges.append((start, end, f"{start:.2f}-{end:.2f}"))
    
    for min_val, max_val, label in ranges:
        if min_val == 0.0:
            # Special case for exactly 0.0
            exact_zero = sum(1 for s in pii_scores if s == 0.0)
            near_zero = sum(1 for s in pii_scores if 0.0 < s < max_val)
            
            if exact_zero > 0:
                pct = (exact_zero / len(pii_scores)) * 100
                bar = '█' * int(pct)
                print(f"  Exactly 0.00   : {exact_zero:6,} ({pct:5.1f}%) {bar}")
            
            if near_zero > 0:
                pct = (near_zero / len(pii_scores)) * 100
                bar = '█' * int(pct)
                print(f"  {f'0.001-{max_val:.2f}':12s}: {near_zero:6,} ({pct:5.1f}%) {bar}")
        else:
            count = sum(1 for s in pii_scores if min_val <= s < max_val)
            if count > 0:
                pct = (count / len(pii_scores)) * 100
                bar = '█' * int(pct)
                print(f"  {label:12s}: {count:6,} ({pct:5.1f}%) {bar}")
    
    print("=" * 80)
    
    # Most common non-zero scores
    non_zero_scores = [s for s in pii_scores if s > 0]
    if non_zero_scores:
        print(f"\n📊 Non-Zero Score Analysis:")
        print(f"  Total with PII indication: {len(non_zero_scores):,} ({len(non_zero_scores)/len(pii_scores)*100:.1f}%)")
        print(f"  Mean of non-zero scores: {statistics.mean(non_zero_scores):.4f}")
        print(f"  Median of non-zero scores: {statistics.median(non_zero_scores):.4f}")
        
        # Round to 2 decimal places for grouping
        rounded_scores = [round(s, 2) for s in non_zero_scores]
        score_counts = Counter(rounded_scores)
        
        print("\n🎯 Most Common Non-Zero PII Scores:")
        for score, count in score_counts.most_common(15):
            pct = (count / len(pii_scores)) * 100
            print(f"  {score:.2f}: {count:,} ({pct:.2f}%)")
    
    # Summary insights
    print("\n💡 Key Insights:")
    zero_count = sum(1 for s in pii_scores if s == 0.0)
    low_risk = sum(1 for s in pii_scores if s < 0.3)
    high_risk = sum(1 for s in pii_scores if s >= 0.7)
    
    print(f"  - {zero_count/len(pii_scores)*100:.1f}% of threads have NO PII (score = 0.0)")
    print(f"  - {low_risk/len(pii_scores)*100:.1f}% are low risk (score < 0.3)")
    print(f"  - {high_risk/len(pii_scores)*100:.1f}% are high risk (score ≥ 0.7)")
    print(f"  - Average PII confidence: {statistics.mean(pii_scores):.4f}")
    
    # Distribution shape
    if statistics.mean(pii_scores) < 0.1:
        print("  - Distribution is heavily skewed toward low PII (good privacy protection)")
    elif statistics.mean(pii_scores) < 0.3:
        print("  - Distribution shows moderate PII presence")
    else:
        print("  - Distribution indicates significant PII presence")

if __name__ == "__main__":
    analyze_pii_scores()