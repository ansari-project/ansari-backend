#!/usr/bin/env python3
"""Generate histogram of PII confidence scores from v2 analysis."""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
from collections import Counter


def analyze_pii_scores():
    """Analyze PII confidence scores and create histogram."""
    output_dir = Path("analyzed_data_v2")

    # Collect all PII scores
    pii_scores = []

    # Read all completed files
    completed_files = sorted(output_dir.glob("analyzed_threads_batch_*.json"))

    print(f"Found {len(completed_files)} completed batch files")

    for file in completed_files:
        try:
            with open(file) as f:
                data = json.load(f)
                for result in data.get("results", []):
                    pii_scores.append(result.get("pii_confidence", 0.0))
        except Exception as e:
            print(f"Error reading {file}: {e}")

    print(f"\nTotal PII scores collected: {len(pii_scores):,}")

    if not pii_scores:
        print("No PII scores found!")
        return

    # Calculate statistics
    pii_array = np.array(pii_scores)

    print("\n📊 PII Confidence Statistics:")
    print(f"  Mean: {np.mean(pii_array):.4f}")
    print(f"  Median: {np.median(pii_array):.4f}")
    print(f"  Std Dev: {np.std(pii_array):.4f}")
    print(f"  Min: {np.min(pii_array):.4f}")
    print(f"  Max: {np.max(pii_array):.4f}")

    # Categorize PII scores
    no_pii = sum(1 for s in pii_scores if s == 0.0)
    very_low = sum(1 for s in pii_scores if 0.0 < s <= 0.1)
    low = sum(1 for s in pii_scores if 0.1 < s <= 0.3)
    medium = sum(1 for s in pii_scores if 0.3 < s <= 0.6)
    high = sum(1 for s in pii_scores if 0.6 < s <= 0.9)
    definite = sum(1 for s in pii_scores if s > 0.9)

    print("\n🔒 PII Categories:")
    print(f"  No PII (0.0): {no_pii:,} ({no_pii / len(pii_scores) * 100:.1f}%)")
    print(f"  Very Low (0.0-0.1): {very_low:,} ({very_low / len(pii_scores) * 100:.1f}%)")
    print(f"  Low (0.1-0.3): {low:,} ({low / len(pii_scores) * 100:.1f}%)")
    print(f"  Medium (0.3-0.6): {medium:,} ({medium / len(pii_scores) * 100:.1f}%)")
    print(f"  High (0.6-0.9): {high:,} ({high / len(pii_scores) * 100:.1f}%)")
    print(f"  Definite (>0.9): {definite:,} ({definite / len(pii_scores) * 100:.1f}%)")

    # Create histogram
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

    # Main histogram with 20 bins
    ax1.hist(pii_scores, bins=20, edgecolor="black", alpha=0.7, color="steelblue")
    ax1.set_xlabel("PII Confidence Score")
    ax1.set_ylabel("Number of Threads")
    ax1.set_title(f"Distribution of PII Confidence Scores (n={len(pii_scores):,})")
    ax1.grid(True, alpha=0.3)

    # Add vertical lines for categories
    ax1.axvline(x=0.1, color="green", linestyle="--", alpha=0.5, label="Very Low threshold")
    ax1.axvline(x=0.3, color="yellow", linestyle="--", alpha=0.5, label="Low threshold")
    ax1.axvline(x=0.6, color="orange", linestyle="--", alpha=0.5, label="Medium threshold")
    ax1.axvline(x=0.9, color="red", linestyle="--", alpha=0.5, label="High threshold")
    ax1.legend()

    # Zoomed histogram for non-zero values
    non_zero_scores = [s for s in pii_scores if s > 0]
    if non_zero_scores:
        ax2.hist(non_zero_scores, bins=30, edgecolor="black", alpha=0.7, color="coral")
        ax2.set_xlabel("PII Confidence Score (excluding 0.0)")
        ax2.set_ylabel("Number of Threads")
        ax2.set_title(f"Distribution of Non-Zero PII Scores (n={len(non_zero_scores):,})")
        ax2.grid(True, alpha=0.3)

        # Add vertical lines for categories
        ax2.axvline(x=0.1, color="green", linestyle="--", alpha=0.5)
        ax2.axvline(x=0.3, color="yellow", linestyle="--", alpha=0.5)
        ax2.axvline(x=0.6, color="orange", linestyle="--", alpha=0.5)
        ax2.axvline(x=0.9, color="red", linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig("pii_histogram.png", dpi=150, bbox_inches="tight")
    print("\n📈 Histogram saved to: pii_histogram.png")

    # Create a more detailed breakdown
    print("\n📊 Detailed Score Distribution:")
    score_ranges = [
        (0.0, 0.0, "Exactly 0.0"),
        (0.01, 0.05, "0.01-0.05"),
        (0.05, 0.1, "0.05-0.10"),
        (0.1, 0.2, "0.10-0.20"),
        (0.2, 0.3, "0.20-0.30"),
        (0.3, 0.4, "0.30-0.40"),
        (0.4, 0.5, "0.40-0.50"),
        (0.5, 0.6, "0.50-0.60"),
        (0.6, 0.7, "0.60-0.70"),
        (0.7, 0.8, "0.70-0.80"),
        (0.8, 0.9, "0.80-0.90"),
        (0.9, 1.0, "0.90-1.00"),
    ]

    for min_val, max_val, label in score_ranges:
        if min_val == 0.0 and max_val == 0.0:
            count = sum(1 for s in pii_scores if s == 0.0)
        else:
            count = sum(1 for s in pii_scores if min_val <= s <= max_val)

        if count > 0:
            pct = count / len(pii_scores) * 100
            bar = "█" * int(pct / 2)  # Create visual bar
            print(f"  {label:12s}: {count:6,} ({pct:5.1f}%) {bar}")

    # Find most common non-zero scores
    non_zero_scores = [s for s in pii_scores if s > 0]
    if non_zero_scores:
        # Round to 2 decimal places for grouping
        rounded_scores = [round(s, 2) for s in non_zero_scores]
        score_counts = Counter(rounded_scores)

        print("\n🎯 Most Common Non-Zero PII Scores:")
        for score, count in score_counts.most_common(10):
            pct = count / len(pii_scores) * 100
            print(f"  {score:.2f}: {count:,} ({pct:.2f}%)")


if __name__ == "__main__":
    analyze_pii_scores()
