#!/usr/bin/env python3
"""Monitor v2 analysis progress every 5 minutes."""

import time
import subprocess
from datetime import datetime


def check_progress():
    """Run the monitor script."""
    try:
        result = subprocess.run(["python3", "monitor_v2_progress.py"], capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(f"Error: {result.stderr}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error running monitor: {e}")


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting monitoring loop (checking every 5 minutes)")

    while True:
        check_progress()

        # Check if analysis is complete
        import json
        from pathlib import Path

        output_dir = Path("analyzed_data_v2")
        completed_files = list(output_dir.glob("analyzed_threads_batch_*.json"))

        if len(completed_files) >= 47:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✅ Analysis complete! All 47 batch files processed.")

            # Final summary
            total_analyzed = 0
            for file in completed_files:
                try:
                    with open(file) as f:
                        data = json.load(f)
                        total_analyzed += data.get("analyzed_threads", 0)
                except (json.JSONDecodeError, OSError):
                    pass

            print(f"Total threads analyzed: {total_analyzed:,}")
            break

        # Wait 5 minutes
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting 5 minutes before next check...")
        time.sleep(300)  # 5 minutes


if __name__ == "__main__":
    main()
