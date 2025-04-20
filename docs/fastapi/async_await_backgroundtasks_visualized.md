# Understanding Async Flow in WhatsApp Integration

This document explains the asynchronous execution flow in the WhatsApp integration, focusing on how control flows between `main_whatsapp.py` and `whatsapp_presenter.py`.

Note 1: to render mermaid diagrams, you can:
* Install this VSCode extension (recommended): [Markdown Preview Mermaid Support](https://marketplace.visualstudio.com/items/?itemName=bierner.markdown-mermaid)
* Alternatively, install this VSCode extension: [Markdown Preview Enhanced](https://marketplace.visualstudio.com/items/?itemName=shd101wyy.markdown-preview-enhanced)
  * Caveat, if you're in dark mode, then text in mermaid diagram will also have a dark color as well, so you may need to change the theme to light mode to see the text clearly.
  * Or, change the theme within the preview menu (bottom right when previewing) to light mode.
* Copy-paste the mermaid code to a live editor like this one: [Mermaid Live Editor](https://mermaid-js.github.io/mermaid-live-editor/)
* Check this file on GitHub (since [it can render mermaid diagrams](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams))


Note 2: If you don't understand the diagrams below, then I suggest checking out the following resource(s) for more information on Python's GIL and async programming:

* Understand Python's GIL: [The Python Global Interpreter Lock (GIL): An (Almost) Love Story](https://medium.com/@amitkhachane.7/the-python-global-interpreter-lock-gil-an-almost-love-story-3acfeff99016)
* Understand async 1 (FastAPI docs): [Concurrency and async / await](https://fastapi.tiangolo.com/async/#async-and-await) (specifically starting from the `async and await` section)
* Understand async 2: [Decoding Asynchronous Programming in Python: Understanding the Basics](https://sunscrapers.com/blog/python-async-programming-basics#:~:text=concurrent%20programming)
* Undertstand async 3: [A Complete Visual Guide to Understanding the Node.js Event Loop](https://www.builder.io/blog/visual-guide-to-nodejs-event-loop#:~:text=within%20a%20callback%20function%20passed%20to)
  * Specifically, the video highlighted in the hyperlink above
* Understand async 4 (to understand the problem's root cause mentioned in this file): [mihi's SO answer](https://stackoverflow.com/a/67601373/13626137)
* Understand async/coroutines in depth: [Mastering Python Async IO with FastAPI](https://dev.to/leapcell/mastering-python-async-io-with-fastapi-13e8)
  * Highly-recommended, but stop before this section: "I/O Multiplexing Technology"
* Understand sync/async/GIL/BackgroundTasks interactions in FastAPI: FastAPI - [Why does synchronous code do not block the event Loop?](https://stackoverflow.com/a/79382844/13626137)
* Finally, using sync vs async in FastAPI: [Dead Simple: When to Use Async in FastAPI](https://hughesadam87.medium.com/dead-simple-when-to-use-async-in-fastapi-0e3259acea6f)


## Initial Concurrency Challenge and Solution - High level Overview

One of the main challenges was ensuring the typing indicator continues to run while the lengthy API call to Claude is processing:

(Note: Similar problem statement can be found on SO [here](https://stackoverflow.com/questions/67599119/fastapi-asynchronous-background-tasks-blocks-other-requests))

```mermaid
sequenceDiagram
    participant P as WhatsAppPresenter
    participant A as AnsariClaude Agent
    participant E as Event Loop

    Note over P,A: Problem: List comprehension blocks event loop
    
    P->>+A: [tok for tok in agent.replace_message_history()]
    
    A->>A: Blocking API call to Claude
    
    Note over E: Event loop blocked ❌
    Note over E: Typing indicator can't run
    
    A-->>-P: Eventually returns all tokens at once
    
    Note over P,A: Solution: Use for loop with await
    
    P->>+A: for token in agent.replace_message_history()
    loop Each token
        A-->>P: yield token
        P->>E: await asyncio.sleep(0)
        Note over E: Event Loop switches tasks ✅
        E->>P: _typing_indicator_loop runs
        E->>P: Continue with next token
    end
    A-->>-P: Complete
```

Below is a more detailed explanation of the solution by visualizing the control flow and how the event loop manages tasks:


## Overview of Control Flow

The WhatsApp integration uses FastAPI's background tasks and asyncio to handle message processing and typing indicators concurrently. Here's a high-level overview:

```mermaid
graph TD
    A[Incoming Webhook Request] --> B[main_webhook function]
    B --> C[Extract message details]
    C --> D[Create user-specific presenter]
    D --> E[Start Background Task 1<br>send_typing_indicator_then_start_loop]
    D --> F[Start Background Task 2<br>handle_text_message]
    E --> G[Send initial typing indicator]
    G --> H[Create Task<br>_typing_indicator_loop]
    F --> I[Process message with agent]
    H --> J[Periodically send<br>typing indicators]
    I --> K[Send final response]
    K --> L[Cancel typing indicator task]
```


## Ultra Detailed Code Execution Flow Traced from Logs

The logs in `async_await_backgroundtasks_logs_for_tracing.log` provide clear evidence of the execution flow described in these diagrams. While the debug logs with "! Before" and "! After" markers may have been removed from the current code, they were strategically placed around critical `await` statements and task creation points to trace how control passes between different parts of the system.

Therefore, this sequence diagram shows the exact order of execution traced from the debug logs, providing a precise view of how control passes between functions and when the event loop switches between tasks:

```mermaid
sequenceDiagram
    participant F as FastAPI
    participant MW as main_webhook
    participant T1 as send_typing_indicator_then_start_loop
    participant T2 as handle_text_message
    participant T3 as _typing_indicator_loop
    participant EL as Event Loop
    
    Note over F,EL: FastAPI receives webhook request
    
    F->>+MW: Execute main_webhook()
    
    Note over MW: Create user_presenter
    MW->>EL: background_tasks.add_task(send_typing_indicator_then_start_loop)
    MW->>EL: background_tasks.add_task(handle_text_message)
    MW-->>-F: Return Response(status_code=200)
    
    Note over F,EL: FastAPI's event loop checks for tasks
    
    EL->>+T1: Execute Task 1
    Note over T1: Set first_indicator_time
    T1->>T1: await _send_whatsapp_typing_indicator()
    Note over T1: Send initial typing indicator to WhatsApp
    T1->>T1: Create Task 3 (_typing_indicator_loop) <br>(Added to event loop)
    T1-->>-EL: Task 1 completes
    
    EL->>+T2: Execute Task 2
    
    Note over T2: Start token processing loop
    T2->>T2: for token in agent.replace_message_history():
    T2->>EL: await asyncio.sleep(0) - first iteration
    
    EL->>+T3: Switch to Task 3
    T3->>EL: await asyncio.sleep(26) - Start waiting
    
    EL->>T2: Resume Task 2
    T2->>T2: response_str += token - continue processing
    
    Note over T2: Continue token processing...
    
    T2->>EL: await asyncio.sleep(0) - middle of iterations
    
    Note over T3: 26 seconds elapsed
    EL->>T3: Resume Task 3
    T3->>EL: await _send_whatsapp_typing_indicator()
    
    EL->>T2: Resume Task 2
    T2->>T2: response_str += token - continue processing
    
    Note over T2: Continue token processing...
    
    T2->>EL: await asyncio.sleep(0) - later in iterations
    
    EL->>T3: _send_whatsapp_typing_indicator() completes
    T3->>EL: await asyncio.sleep(26) - Start next wait
    
    EL->>T2: Resume Task 2
    
    Note over T2: Final token processing...
    
    T2->>T2: Processing complete
    T2->>EL: await send_whatsapp_message()

    Note over EL: Task 3 is still in the 26-second wait <br>(so event loop won't resume it yet)
    EL->>T2: Resume Task 2
    
    T2->>T2: Cancel typing_indicator_task <br>(Removed from event loop)
    T2-->>-EL: Task 2 completes
    
    Note over EL: All tasks complete
```

## Key Insights

1. **FastAPI Background Tasks**: 
   - FastAPI's background tasks allow tasks to continue after the HTTP response has been sent
   - In our case, two tasks are created: typing indicator and message processing

2. **Task Creation and Execution Order**:
   - Tasks are executed in the order they're added to the event loop
   - The typing indicator task is added first, ensuring it starts before message processing

3. **Proper Yielding Points**:
   - `await asyncio.sleep(0)` is strategically placed in the token processing loop
   - This allows the typing indicator task to run periodically during message processing

4. **Task Cancellation**:
   - The typing indicator task is explicitly cancelled when message processing completes
   - This prevents the typing indicator from continuing after the response is sent

5. **The Critical Role of `async with`**:
   - `async with httpx.AsyncClient()` ensures proper asynchronous resource management
   - Both client creation and cleanup happen asynchronously without blocking the event loop

## Common Pitfalls and Solutions

| Pitfall                      | Problem                                                         | Solution                                                                      |
| ---------------------------- | --------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Blocking operations          | List comprehensions, synchronous API calls block the event loop | Replace with `for` loops and add periodic `await asyncio.sleep(0)` statements |
| Missing yield points         | Long-running operations prevent other tasks from executing      | Add strategic `await` statements to yield control                             |
| Forgotten task cancellation  | Background tasks continue running indefinitely                  | Explicitly call `task.cancel()` when the task is no longer needed             |
| Improper resource management | Using `with` instead of `async with` for async resources        | Always use `async with` for asynchronous context managers                     |
| Task execution order         | Critical tasks start too late                                   | Pay attention to the order in which tasks are added to the event loop         |

