***TOC:***

- [FastAPI Sync vs Async Endpoints: Event Loop and Thread Handling](#fastapi-sync-vs-async-endpoints-event-loop-and-thread-handling)
  - [Overview](#overview)
  - [How FastAPI Handles Different Endpoint Types](#how-fastapi-handles-different-endpoint-types)
    - [Synchronous (`def`) Endpoints](#synchronous-def-endpoints)
    - [Asynchronous (`async def`) Endpoints](#asynchronous-async-def-endpoints)
  - [Debug Function Analysis: `debug_event_loop_context()`](#debug-function-analysis-debug_event_loop_context)
    - [Behavior in Different Contexts](#behavior-in-different-contexts)
      - [When Called from `def` Endpoints:](#when-called-from-def-endpoints)
      - [When Called from `async def` Endpoints:](#when-called-from-async-def-endpoints)
  - [Case Study: `_translate_with_event_loop_safety()` Method](#case-study-_translate_with_event_loop_safety-method)
    - [Why This Try/Except Block Is Needed](#why-this-tryexcept-block-is-needed)
    - [Performance Implications](#performance-implications)
  - [Best Practices](#best-practices)
    - [Choose Sync (`def`) When:](#choose-sync-def-when)
    - [Choose Async (`async def`) When:](#choose-async-async-def-when)
    - [Avoid Common Pitfalls:](#avoid-common-pitfalls)
  - [References](#references)
  - [Extra - How to Test Event Loop Behavior Yourself](#extra---how-to-test-event-loop-behavior-yourself)
    - [Step 1: Import the Debug Function](#step-1-import-the-debug-function)
    - [Step 2: Add Debug Calls to Different Endpoint Types](#step-2-add-debug-calls-to-different-endpoint-types)
      - [In Sync (`def`) Endpoints:](#in-sync-def-endpoints)
      - [In Async (`async def`) Endpoints:](#in-async-async-def-endpoints)
      - [In Translation Functions:](#in-translation-functions)
    - [Step 3: Test and Observe](#step-3-test-and-observe)
    - [Expected Output Differences](#expected-output-differences)
  - [Related Code Files](#related-code-files)


# FastAPI Sync vs Async Endpoints: Event Loop and Thread Handling

## Overview

This document explains the fundamental differences between synchronous (`def`) and asynchronous (`async def`) endpoint definitions in FastAPI, particularly focusing on how they interact with event loops and thread management. Understanding these differences is crucial for making informed decisions about endpoint design and for debugging event loop-related issues.

## How FastAPI Handles Different Endpoint Types

### Synchronous (`def`) Endpoints

When you declare a path operation function with normal `def` instead of `async def`, FastAPI handles it differently to prevent blocking the server:

- **Thread Pool Execution**: The function runs in an external threadpool managed by FastAPI
- **Thread Assignment**: When a request comes in, Uvicorn detects the synchronous nature and assigns it to one of the threads in the thread pool
- **Non-blocking**: The main event loop awaits the threadpool execution, preventing server blocking
- **Concurrency Limitation**: The number of concurrent synchronous requests is limited by the thread pool size (default: 40 threads)

**Key Characteristic**: **No running event loop context** - these functions execute in separate threads outside the main event loop.

### Asynchronous (`async def`) Endpoints

Asynchronous endpoints are handled directly by the event loop:

- **Event Loop Execution**: Functions run directly within the event loop on the main thread
- **Single Thread**: All async operations share the same main thread created when running the server
- **Cooperative Multitasking**: When an endpoint reaches an `await` statement, the event loop can switch to handle other requests
- **High Concurrency**: Can handle thousands of concurrent requests on a single thread

**Key Characteristic**: **Running event loop context** - these functions execute within the active event loop.

## Debug Function Analysis: `debug_event_loop_context()`

The `debug_event_loop_context()` function in `debug_utils.py` demonstrates these differences by checking the current execution context:

```python
def debug_event_loop_context(location: str):
    """Debug function to analyze the event loop context."""
    logger.debug(f"\n=== DEBUG: {location} ===")
    logger.debug(f"Thread ID: {threading.get_ident()}")
    
    try:
        loop = asyncio.get_running_loop()
        logger.debug(f"Running loop: {id(loop)}")
        logger.debug(f"Loop is running: {loop.is_running()}")
        current_task = asyncio.current_task()
        logger.debug(f"Current task: {current_task}")
    except RuntimeError as e:
        logger.debug(f"No running loop: {e}")
```

### Behavior in Different Contexts

#### When Called from `def` Endpoints:
- **Thread ID**: Shows a different thread ID (from the threadpool)
- **Event Loop**: Throws `RuntimeError: There is no current event loop running in thread`
- **Result**: Logs "No running loop" message

#### When Called from `async def` Endpoints:
- **Thread ID**: Shows the main thread ID
- **Event Loop**: Successfully retrieves the running loop
- **Result**: Logs loop ID, running status, and current task information

## Case Study: `_translate_with_event_loop_safety()` Method

The `_translate_with_event_loop_safety()` method in `ansari_claude.py` demonstrates a practical application of this knowledge:

```python
def _translate_with_event_loop_safety(self, arabic_texts: list[str], context: str = "citation") -> list[str]:
    """Safely translate multiple Arabic texts to English, handling both event loop contexts."""
    if not arabic_texts:
        return []

    try:
        # First try to use asyncio.run() (works when not in event loop)
        logger.info(f"Attempting parallel translation using asyncio.run() for {context}")
        return asyncio.run(translate_texts_parallel(arabic_texts, "en", "ar"))
    except RuntimeError as e:
        # If we get RuntimeError, we're already in an event loop
        logger.info(f"asyncio.run() failed ({e}), using sequential translation to avoid complexity")
        from ansari.util.translation import translate_text
        
        results = []
        for text in arabic_texts:
            result = translate_text(text, "en", "ar")
            results.append(result)
        return results
```

### Why This Try/Except Block Is Needed

The try/except block handles two different execution contexts:

1. **When called from sync (`def`) endpoints**:
   - No event loop is running in the current thread
   - `asyncio.run()` succeeds and creates a new event loop
   - Can use `translate_texts_parallel()` for efficient parallel processing

2. **When called from async (`async def`) endpoints or background tasks**:
   - An event loop is already running
   - `asyncio.run()` raises `RuntimeError: cannot be called from a running event loop`
   - Falls back to sequential processing using `translate_text()`

### Performance Implications

- **Sync Context**: Benefits from parallel translation processing
- **Async Context**: Uses sequential processing to avoid event loop conflicts
- **Trade-off**: Sacrifices some performance in async contexts for code stability

## Best Practices

### Choose Sync (`def`) When:
- Performing CPU-bound operations
- Using libraries that don't support async/await
- Simple, straightforward operations that don't require high concurrency

### Choose Async (`async def`) When:
- Handling I/O-bound operations (database queries, API calls, file operations)
- Requiring high concurrency
- Building real-time applications (chat, live data processing)

### Avoid Common Pitfalls:
- **Don't call `asyncio.run()` from within async contexts** - it will raise RuntimeError
- **Don't block the event loop** in async endpoints without yielding control
- **Consider using `asyncio.create_task()` or `run_in_executor()`** for running async code from sync contexts

## References

- [FastAPI Official Documentation - Async/Await](https://fastapi.tiangolo.com/async/)
- [Python Features - When to define our Endpoint Sync or Async in FastAPI](https://medium.com/python-features/when-to-define-our-endpoint-sync-or-async-in-fastapi-6065238f2b34#0534)
- [Python asyncio Documentation](https://docs.python.org/3/library/asyncio.html)

## Extra - How to Test Event Loop Behavior Yourself

To verify the different event loop behaviors between sync and async endpoints, you can temporarily add debug calls to your code:

### Step 1: Import the Debug Function
Add this import to any file where you want to test:
```python
from ansari.util.debug_utils import debug_event_loop_context
```

### Step 2: Add Debug Calls to Different Endpoint Types

#### In Sync (`def`) Endpoints:
```python
# Example in src/ansari/app/main_api.py - add_message() function
def add_message(...):
    debug_event_loop_context("add_message() function")
    # ... rest of function
```

#### In Async (`async def`) Endpoints:
```python
# Example in src/ansari/app/main_whatsapp.py - main_webhook() function
async def main_webhook(...):
    debug_event_loop_context("main_webhook() function WA")
    # ... rest of function
```

#### In Translation Functions:
```python
# Example in src/ansari/agents/ansari_claude.py - _translate_with_event_loop_safety() method
def _translate_with_event_loop_safety(self, arabic_texts: list[str], context: str = "citation") -> list[str]:
    debug_event_loop_context("translate_with_event_loop_safety() function")
    # ... rest of function

# Example in src/ansari/util/translation.py
def translate_text(...):
    debug_event_loop_context("translate_text() function")
    # ... rest of function

async def translate_texts_parallel(...):
    debug_event_loop_context("translate_texts_parallel() function")
    # ... rest of function
```

### Step 3: Test and Observe
1. Start your FastAPI server
2. Make requests to both sync and async endpoints
3. Check the logs to see the different thread IDs and event loop contexts
4. **Important**: Remove these debug calls after testing to keep the code clean

### Expected Output Differences

**From Sync Endpoints** (different thread, no event loop):
```
=== DEBUG: add_message() function ===
Thread ID: 12345
No running loop: There is no current event loop running in thread
```

**From Async Endpoints** (main thread, with event loop):
```
=== DEBUG: main_webhook() function WA ===
Thread ID: 67890
Running loop: 140123456789
Loop is running: True
Current task: <Task pending name='Task-1' coro=<main_webhook()>>
```

## Related Code Files

- `src/ansari/util/debug_utils.py` - Debug utility for event loop context analysis
- `src/ansari/agents/ansari_claude.py:1479` - `_translate_with_event_loop_safety()` method implementation
- `src/ansari/app/main_api.py` - Sync endpoint examples (e.g., `add_message()`)
- `src/ansari/app/main_whatsapp.py` - Async endpoint examples (e.g., `main_webhook()`)