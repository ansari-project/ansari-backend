#!/usr/bin/env python3
"""
Analyze tool usage by counting unique threads that use each tool.
"""

import json
from pathlib import Path


def analyze_tool_usage_by_threads(data_dir: str):
    """Count unique threads that use each tool."""
    data_path = Path(data_dir)
    index_file = data_path / "index.json"

    with open(index_file, "r", encoding="utf-8") as f:
        index_data = json.load(f)

    # Track unique threads per tool
    threads_per_tool = {"search_quran": set(), "search_hadith": set(), "search_mawsuah": set(), "search_tafsir_encyc": set()}

    total_threads = 0
    analyzable_threads = 0
    threads_with_tools = set()

    for batch_file in index_data["files"]:
        batch_path = Path(batch_file)
        if not batch_path.is_absolute():
            batch_path = data_path / batch_path.name

        with open(batch_path, "r", encoding="utf-8") as f:
            threads = json.load(f)

        for thread in threads:
            thread_id = thread.get("_id")
            total_threads += 1

            # Check if thread has user messages (is analyzable)
            has_user_message = False
            for message in thread.get("messages", []):
                if message.get("role") == "user":
                    has_user_message = True
                    break

            if has_user_message:
                analyzable_threads += 1

            # Check for tool usage
            for message in thread.get("messages", []):
                content = message.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            tool_name = item.get("name")
                            if tool_name and thread_id:
                                if tool_name in threads_per_tool:
                                    threads_per_tool[tool_name].add(thread_id)
                                threads_with_tools.add(thread_id)

    return {
        "total_threads": total_threads,
        "analyzable_threads": analyzable_threads,
        "threads_with_tools": len(threads_with_tools),
        "threads_per_tool": {tool: len(threads) for tool, threads in threads_per_tool.items()},
    }


# Run analysis
print("Analyzing unique threads per tool...")
results = analyze_tool_usage_by_threads("data")

# Print results
print(f"\n{'=' * 80}")
print("TOOL USAGE BY UNIQUE THREADS")
print(f"{'=' * 80}")

print("\nTHREAD STATISTICS:")
print(f"  Total threads: {results['total_threads']:,}")
print(f"  Analyzable threads: {results['analyzable_threads']:,}")
print(f"  Threads with tools: {results['threads_with_tools']:,}")
print(f"  Tool adoption rate: {results['threads_with_tools'] / results['analyzable_threads'] * 100:.1f}%")

print("\nUNIQUE THREADS PER TOOL:")
print(f"{'Tool':<25} {'Unique Threads':>15} {'% of Analyzable':>18}")
print("-" * 60)
for tool, count in sorted(results["threads_per_tool"].items(), key=lambda x: x[1], reverse=True):
    percentage = (count / results["analyzable_threads"]) * 100
    print(f"{tool:<25} {count:>15,} {percentage:>17.1f}%")

print("\nKEY INSIGHTS:")
tool_counts = results["threads_per_tool"]
analyzable = results["analyzable_threads"]
quran_pct = tool_counts["search_quran"] / analyzable * 100
hadith_pct = tool_counts["search_hadith"] / analyzable * 100
mawsuah_pct = tool_counts["search_mawsuah"] / analyzable * 100
tafsir_pct = tool_counts["search_tafsir_encyc"] / analyzable * 100
print(f"  - {tool_counts['search_quran']:,} threads ({quran_pct:.1f}%) use search_quran")
print(f"  - {tool_counts['search_hadith']:,} threads ({hadith_pct:.1f}%) use search_hadith")
print(f"  - {tool_counts['search_mawsuah']:,} threads ({mawsuah_pct:.1f}%) use search_mawsuah")
print(f"  - {tool_counts['search_tafsir_encyc']:,} threads ({tafsir_pct:.1f}%) use search_tafsir_encyc")
