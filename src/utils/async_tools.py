"""Async utilities integrating asyncio with Kivy's main thread."""
import asyncio
import threading
from typing import Coroutine, Any, Callable, Optional
from kivy.clock import Clock
from src.core.logger import logger


class AsyncBridge:
    """Runs a dedicated background asyncio event loop and dispatches results to Kivy main thread."""

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._ensure_loop()

    def _ensure_loop(self):
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._run_event_loop, daemon=True, name="AsyncBridgeThread")
                self._thread.start()

    def _run_event_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def get_loop(self) -> asyncio.AbstractEventLoop:
        self._ensure_loop()
        return self._loop

    def run_async(
        self,
        coro: Coroutine[Any, Any, Any],
        on_success: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        """
        Executes an asyncio coroutine in the background event loop
        and safely invokes on_success/on_error on Kivy's main thread.
        """
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _on_future_done(fut):
            try:
                exc = fut.exception()
                if exc:
                    logger.error("Async task error: %s", exc, exc_info=True)
                    if on_error:
                        Clock.schedule_once(lambda dt: on_error(exc), 0)
                else:
                    res = fut.result()
                    if on_success:
                        Clock.schedule_once(lambda dt: on_success(res), 0)
            except Exception as e:
                logger.error("Error in async task callback: %s", e, exc_info=True)
                if on_error:
                    Clock.schedule_once(lambda dt: on_error(e), 0)

        future.add_done_callback(_on_future_done)
        return future

    def stop(self):
        """Stops the background event loop."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)


_bridge = AsyncBridge()


def run_async(coro: Coroutine[Any, Any, Any], on_success: Optional[Callable] = None, on_error: Optional[Callable] = None):
    """Executes a coroutine in background asyncio loop, delivering result to Kivy main thread."""
    return _bridge.run_async(coro, on_success=on_success, on_error=on_error)


def schedule_on_main(callback: Callable, *args, **kwargs):
    """Schedules a function to run on Kivy's main thread."""
    Clock.schedule_once(lambda dt: callback(*args, **kwargs), 0)
