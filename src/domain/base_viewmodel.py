"""Base ViewModel for reactive MVVM architecture in Kivy."""
from typing import Coroutine, Any, Callable, Optional
from kivy.event import EventDispatcher
from kivy.properties import BooleanProperty, StringProperty
from src.utils.async_tools import run_async
from src.core.logger import logger


class BaseViewModel(EventDispatcher):
    """Base class for all screen ViewModels providing reactive state properties."""
    
    is_loading = BooleanProperty(False)
    error_message = StringProperty("")

    def run_task(
        self,
        coro: Coroutine[Any, Any, Any],
        on_success: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        show_loader: bool = True
    ):
        """Runs an async task updating `is_loading` and handling errors reactively."""
        if show_loader:
            self.is_loading = True
            self.error_message = ""

        def _on_success_wrapper(result):
            if show_loader:
                self.is_loading = False
            if on_success:
                on_success(result)

        def _on_error_wrapper(exc: Exception):
            if show_loader:
                self.is_loading = False
            self.error_message = str(exc)
            logger.error("ViewModel task error: %s", exc)
            if on_error:
                on_error(exc)

        return run_async(coro, on_success=_on_success_wrapper, on_error=_on_error_wrapper)
