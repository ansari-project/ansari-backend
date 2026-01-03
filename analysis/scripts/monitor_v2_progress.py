#!/usr/bin/env python3
"""Monitor v2 analysis progress."""

import json
from pathlib import Path
from datetime import datetime


def check_progress():
    """Check current progress of v2 analysis."""
    output_dir = Path("analyzed_data_v2")

    if not output_dir.exists():
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Output directory not created yet")
        return

    completed_files = list(output_dir.glob("analyzed_threads_batch_*.json"))

    if not completed_files:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No completed files yet")
        return

    total_analyzed = 0
    total_threads = 0

    for file in completed_files:
        try:
            with open(file) as f:
                data = json.load(f)
                total_threads += data.get("total_threads", 0)
                total_analyzed += data.get("analyzed_threads", 0)
        except (json.JSONDecodeError, OSError):
            pass

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Progress Report:")
    print(f"  Completed batch files: {len(completed_files)}/47")
    print(f"  Threads analyzed: {total_analyzed:,}")
    print(f"  Percentage: {len(completed_files) / 47 * 100:.1f}%")

    # List completed files
    if completed_files:
        print(f"  Completed: {', '.join([f.stem.split('_')[-1] for f in sorted(completed_files)])}")


if __name__ == "__main__":
    check_progress()
