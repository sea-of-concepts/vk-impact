"""Media cache manager for asynchronous disk caching of avatars and attachments."""
import hashlib
from pathlib import Path
from typing import Optional, Dict, Callable
from src.core.config import config
from src.core.logger import logger
from src.data.api.http_client import create_http_session
from src.utils.async_tools import run_async


class MediaCacheManager:
    """Manages disk and memory caching of remote image assets."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or (config.CACHE_DIR / "images")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, str] = {}
        self._pending_downloads: Dict[str, list] = {}

    def _get_cache_path(self, url: str) -> Path:
        """Generates deterministic filename based on URL hash."""
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        ext = ".jpg"
        if ".png" in url.lower():
            ext = ".png"
        elif ".gif" in url.lower():
            ext = ".gif"
        return self.cache_dir / f"{url_hash}{ext}"

    def get_local_path(self, url: str) -> Optional[str]:
        """Returns local file path if already cached, else None."""
        if not url or not url.startswith("http"):
            return url if url else None

        if url in self._memory_cache:
            return self._memory_cache[url]

        target_file = self._get_cache_path(url)
        if target_file.exists() and target_file.stat().st_size > 0:
            local_str = str(target_file)
            self._memory_cache[url] = local_str
            return local_str

        return None

    def fetch_image_async(self, url: str, on_ready: Optional[Callable[[str], None]] = None):
        """
        Retrieves local cached path immediately or downloads in background
        and notifies on_ready callback.
        """
        if not url or not url.startswith("http"):
            if on_ready:
                on_ready(url or "")
            return

        local = self.get_local_path(url)
        if local:
            from src.core.log_collector import log_collector
            log_collector.log_media("Image", url, is_hit=True)
            if on_ready:
                on_ready(local)
            return

        # Queue callback if already downloading
        if url in self._pending_downloads:
            if on_ready:
                self._pending_downloads[url].append(on_ready)
            return

        self._pending_downloads[url] = [on_ready] if on_ready else []

        async def _download():
            target_file = self._get_cache_path(url)
            async with create_http_session(timeout_seconds=15.0) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        with open(target_file, "wb") as f:
                            f.write(content)
                        return str(target_file)
            return ""

        def _on_success(local_path: str):
            from src.core.log_collector import log_collector
            log_collector.log_media("Image", url, is_hit=False)
            callbacks = self._pending_downloads.pop(url, [])
            if local_path:
                self._memory_cache[url] = local_path
                for cb in callbacks:
                    if cb:
                        cb(local_path)
            else:
                for cb in callbacks:
                    if cb:
                        cb(url)

        def _on_error(exc: Exception):
            callbacks = self._pending_downloads.pop(url, [])
            for cb in callbacks:
                if cb:
                    cb(url)

        run_async(_download(), on_success=_on_success, on_error=_on_error)


media_cache = MediaCacheManager()
