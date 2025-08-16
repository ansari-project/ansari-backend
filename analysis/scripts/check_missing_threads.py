#!/usr/bin/env python3
"""
Quick script to understand why 1,006 threads weren't analyzed.
"""

import json
from pathlib import Path

def extract_first_user_message(thread):
    """Extract first user message from a thread."""
    messages = thread.get("messages", [])
    for message in messages:
        if message.get("role") == "user":
            content = message.get("content", [])
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                first_message = " ".join(text_parts).strip()
            elif isinstance(content, str):
                first_message = content.strip()
            else:
                first_message = ""
            return first_message
    return ""

def analyze_missing():
    """Find out why threads were skipped."""
    
    data_dir = Path("data")
    total_threads = 0
    threads_with_messages = 0
    threads_with_empty_messages = 0
    threads_with_no_user_messages = 0
    
    print("Checking all thread files for missing user messages...")
    
    for batch_file in sorted(data_dir.glob("threads_batch_*.json")):
        with open(batch_file) as f:
            threads = json.load(f)
        
        for thread in threads:
            total_threads += 1
            first_message = extract_first_user_message(thread)
            
            if first_message:
                threads_with_messages += 1
            else:
                # Check if there are any user messages at all
                has_user_message = any(
                    msg.get("role") == "user" 
                    for msg in thread.get("messages", [])
                )
                
                if has_user_message:
                    threads_with_empty_messages += 1
                    if threads_with_empty_messages <= 3:  # Show first few examples
                        print(f"\nExample empty user message thread {thread.get('_id')}:")
                        for msg in thread.get("messages", [])[:3]:
                            if msg.get("role") == "user":
                                print(f"  User message: {msg.get('content')}")
                else:
                    threads_with_no_user_messages += 1
                    if threads_with_no_user_messages <= 3:  # Show first few examples
                        print(f"\nExample thread with no user messages {thread.get('_id')}:")
                        for msg in thread.get("messages", [])[:3]:
                            print(f"  {msg.get('role', 'unknown')}: {str(msg.get('content', ''))[:100]}...")
    
    print(f"\n" + "="*60)
    print(f"ANALYSIS OF MISSING THREADS")
    print(f"="*60)
    print(f"Total threads in data: {total_threads}")
    print(f"Threads with extractable first user message: {threads_with_messages}")
    print(f"Threads with empty/whitespace user messages: {threads_with_empty_messages}")
    print(f"Threads with no user messages at all: {threads_with_no_user_messages}")
    print(f"Missing threads (should be 1,006): {total_threads - threads_with_messages}")

if __name__ == "__main__":
    analyze_missing()