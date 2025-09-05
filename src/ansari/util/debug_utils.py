import asyncio
import threading
from ansari.ansari_logger import get_logger

logger = get_logger(__name__)

def debug_event_loop_context(location: str):
    """
    Debug function to analyze the event loop context.
    This function is used to prove or double-check that `async def` FastAPI endpoints 
    run within an event loop, while `def` (synchronous) functions execute on separate 
    threads and not inside the event loop of the main thread.
    Args:
        location (str): A string identifier to indicate the location or context 
                        from where this function is called, useful for logging.
    Logs:
        - Thread ID of the current execution context.
        - Whether there is a running event loop and its ID.
        - Whether the loop is currently running.
        - The current asyncio task, if any.
        - A message indicating the absence of a running event loop, if applicable.
    """
    logger.debug(f"\n=== DEBUG: {location} ===")
    logger.debug(f"Thread ID: {threading.get_ident()}")
    
    try:
        loop = asyncio.get_running_loop()
        logger.debug(f"Running loop: {id(loop)}")
        logger.debug(f"Loop is running: {loop.is_running()}")
        
        # Try to detect if we're in a task
        current_task = asyncio.current_task()
        logger.debug(f"Current task: {current_task}")
        
    except RuntimeError as e:
        logger.debug(f"No running loop: {e}")
