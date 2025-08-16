#!/usr/bin/env python3
"""
Comprehensive tool usage analysis across all threads.
"""

import json
from pathlib import Path
from collections import Counter
from datetime import datetime

def analyze_tool_usage(data_dir: str):
    """Analyze tool usage patterns across all threads."""
    data_path = Path(data_dir)
    index_file = data_path / "index.json"
    
    with open(index_file, "r", encoding="utf-8") as f:
        index_data = json.load(f)
    
    tool_counts = Counter()
    tool_by_month = {}
    total_threads = 0
    threads_with_tools = 0
    total_messages = 0
    messages_with_tools = 0
    tool_combinations = Counter()
    
    for batch_file in index_data['files']:
        batch_path = Path(batch_file)
        if not batch_path.is_absolute():
            batch_path = data_path / batch_path.name
        
        with open(batch_path, "r", encoding="utf-8") as f:
            threads = json.load(f)
        
        for thread in threads:
            total_threads += 1
            thread_tools = set()
            
            for message in thread.get("messages", []):
                total_messages += 1
                message_tools = set()
                
                # Check content array
                content = message.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            tool_name = item.get("name")
                            if tool_name:
                                tool_counts[tool_name] += 1
                                thread_tools.add(tool_name)
                                message_tools.add(tool_name)
                                
                                # Track by month
                                thread_date = thread.get("updated_at", thread.get("created_at"))
                                if thread_date:
                                    month = thread_date[:7]  # YYYY-MM
                                    if month not in tool_by_month:
                                        tool_by_month[month] = Counter()
                                    tool_by_month[month][tool_name] += 1
                
                if message_tools:
                    messages_with_tools += 1
            
            if thread_tools:
                threads_with_tools += 1
                if len(thread_tools) > 1:
                    tool_combinations[tuple(sorted(thread_tools))] += 1
    
    return {
        "tool_counts": tool_counts,
        "tool_by_month": tool_by_month,
        "total_threads": total_threads,
        "threads_with_tools": threads_with_tools,
        "total_messages": total_messages,
        "messages_with_tools": messages_with_tools,
        "tool_combinations": tool_combinations
    }

# Run analysis
print("Analyzing tool usage across all threads...")
results = analyze_tool_usage("data")

# Print results
print(f"\n{'='*80}")
print("TOOL USAGE ANALYSIS REPORT")
print(f"{'='*80}")

print(f"\nOVERALL STATISTICS:")
print(f"  Total threads: {results['total_threads']:,}")
print(f"  Threads with tool usage: {results['threads_with_tools']:,} ({results['threads_with_tools']/results['total_threads']*100:.1f}%)")
print(f"  Total messages: {results['total_messages']:,}")
print(f"  Messages with tool usage: {results['messages_with_tools']:,} ({results['messages_with_tools']/results['total_messages']*100:.1f}%)")

print(f"\nTOOL USAGE FREQUENCY:")
print(f"{'Tool Name':<30} {'Count':>10} {'Percentage':>12}")
print("-" * 55)
total_tool_uses = sum(results['tool_counts'].values())
for tool, count in results['tool_counts'].most_common():
    percentage = (count / total_tool_uses) * 100 if total_tool_uses > 0 else 0
    print(f"{tool:<30} {count:>10,} {percentage:>11.1f}%")

print(f"\nTOOL USAGE BY MONTH:")
months = sorted(results['tool_by_month'].keys())
if months:
    print(f"{'Month':<10}", end="")
    all_tools = set()
    for month_tools in results['tool_by_month'].values():
        all_tools.update(month_tools.keys())
    
    # Print top 5 tools as columns
    top_tools = [tool for tool, _ in results['tool_counts'].most_common(5)]
    for tool in top_tools[:5]:
        print(f" {tool[:15]:>15}", end="")
    print()
    print("-" * (10 + 16 * min(5, len(top_tools))))
    
    for month in months:
        print(f"{month:<10}", end="")
        for tool in top_tools[:5]:
            count = results['tool_by_month'][month].get(tool, 0)
            print(f" {count:>15,}", end="")
        print()

print(f"\nTOOL COMBINATIONS (threads using multiple tools):")
if results['tool_combinations']:
    print(f"{'Tool Combination':<50} {'Count':>10}")
    print("-" * 62)
    for tools, count in results['tool_combinations'].most_common(10):
        tools_str = " + ".join(tools)
        if len(tools_str) > 48:
            tools_str = tools_str[:45] + "..."
        print(f"{tools_str:<50} {count:>10}")

# Save results to JSON
output_file = Path("analysis/data-local/tool_usage_analysis.json")
output_file.parent.mkdir(parents=True, exist_ok=True)

with open(output_file, "w", encoding="utf-8") as f:
    # Convert Counter objects to dicts for JSON serialization
    json_results = {
        "tool_counts": dict(results['tool_counts']),
        "tool_by_month": {month: dict(counts) for month, counts in results['tool_by_month'].items()},
        "total_threads": results['total_threads'],
        "threads_with_tools": results['threads_with_tools'],
        "total_messages": results['total_messages'],
        "messages_with_tools": results['messages_with_tools'],
        "tool_combinations": {" + ".join(tools): count for tools, count in results['tool_combinations'].items()},
        "summary": {
            "tool_usage_rate_threads": f"{results['threads_with_tools']/results['total_threads']*100:.1f}%",
            "tool_usage_rate_messages": f"{results['messages_with_tools']/results['total_messages']*100:.1f}%",
            "total_tool_invocations": total_tool_uses,
            "unique_tools_used": len(results['tool_counts'])
        }
    }
    json.dump(json_results, f, indent=2)

print(f"\nResults saved to: {output_file}")