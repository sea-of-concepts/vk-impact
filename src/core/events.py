"""Global event bus for decoupled communication with safe main-thread dispatching."""
import asyncio
import threading
from typing import Callable, Dict, List, Any
from src.core.logger import logger


class EventBus:
    """Pub/Sub event dispatcher ensuring UI thread-safety across background workers."""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_name: str, callback: Callable) -> None:
        """Subscribes a callback to an event."""
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable) -> None:
        """Unsubscribes a callback from an event."""
        if event_name in self._subscribers and callback in self._subscribers[event_name]:
            self._subscribers[event_name].remove(callback)

    def emit(self, event_name: str, **kwargs) -> None:
        """
        Emits an event:
        - If already on the main thread: executes subscribers immediately.
        - If on a background worker thread: schedules execution onto the Kivy main thread.
        """
        if event_name not in self._subscribers:
            return

        def _dispatch(*args):
            for callback in list(self._subscribers.get(event_name, [])):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        from src.utils.async_tools import run_async
                        run_async(callback(**kwargs))
                    else:
                        callback(**kwargs)
                except Exception as e:
                    logger.error("Error executing callback for event %s: %s", event_name, e)

        # If already on main thread, execute synchronously
        if threading.current_thread() is threading.main_thread():
            _dispatch()
        else:
            # Transfer execution to Kivy main thread
            try:
                from kivy.clock import Clock
                Clock.schedule_once(_dispatch, 0)
            except Exception:
                _dispatch()


event_bus = EventBus()
