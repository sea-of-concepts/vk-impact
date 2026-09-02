"""Asynchronous VK API Client with rate limiting and error handling."""
import asyncio
import time
import random
from typing import Optional, Dict, Any, List, Union
import aiohttp
from src.core.config import config
from src.core.logger import logger
from src.data.api.models import VKUser, VKConversation, VKMessage


class VKApiError(Exception):
    """Exception raised on VK API errors."""
    def __init__(self, code: int, message: str, raw_response: Dict[str, Any]):
        super().__init__(f"VK API Error [{code}]: {message}")
        self.code = code
        self.message = message
        self.raw_response = raw_response


from src.data.api.http_client import create_http_session


class VKApiClient:
    """High-performance non-blocking VK API Client."""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self._session: Optional[aiohttp.ClientSession] = None
        # Rate limit: 3 requests per second limit for user tokens
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_time = 0.0
        self._min_request_interval = 0.34  # ~3 req/sec

    def set_token(self, token: str) -> None:
        """Sets or updates the active user access token."""
        self.access_token = token

    async def _get_session(self) -> aiohttp.ClientSession:
        """Returns or creates aiohttp session with SSL support."""
        if self._session is None or self._session.closed:
            self._session = create_http_session(timeout_seconds=15.0)
        return self._session

    async def close(self) -> None:
        """Closes the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _throttle(self) -> None:
        """Ensures we respect the VK API rate limit (<= 3 req/sec)."""
        async with self._rate_limit_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._min_request_interval:
                await asyncio.sleep(self._min_request_interval - elapsed)
            self._last_request_time = time.monotonic()

    async def request(self, method: str, params: Optional[Dict[str, Any]] = None, retries: int = 2) -> Dict[str, Any]:
        """
        Executes a VK API method call.
        """
        if not self.access_token:
            raise VKApiError(5, "Access token not set", {})

        url = f"{config.VK_API_BASE_URL}{method}"
        payload = {
            "v": config.VK_API_VERSION,
            "access_token": self.access_token,
            **(params or {})
        }

        # Filter out None values
        payload = {k: v for k, v in payload.items() if v is not None}

        session = await self._get_session()
        start_time = time.monotonic()

        for attempt in range(retries + 1):
            await self._throttle()
            try:
                async with session.post(url, data=payload, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    duration_ms = (time.monotonic() - start_time) * 1000
                    data = await response.json()
                    
                    if "error" in data:
                        err = data["error"]
                        err_code = err.get("error_code", 0)
                        err_msg = err.get("error_msg", "Unknown error")
                        
                        # Rate limit exceeded (error 6) or temporary server issue (error 10)
                        if err_code in (6, 10) and attempt < retries:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                            
                        from src.core.log_collector import log_collector
                        log_collector.log_api(
                            method,
                            status=response.status,
                            duration_ms=duration_ms,
                            error=err_msg,
                            params=payload,
                            response_data=data
                        )
                        raise VKApiError(err_code, err_msg, data)
                        
                    from src.core.log_collector import log_collector
                    log_collector.log_api(
                        method,
                        status=response.status,
                        duration_ms=duration_ms,
                        params=payload,
                        response_data=data
                    )
                    return data.get("response", {})
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                duration_ms = (time.monotonic() - start_time) * 1000
                from src.core.log_collector import log_collector
                log_collector.log_api(
                    method,
                    status=500,
                    duration_ms=duration_ms,
                    error=str(e),
                    params=payload
                )
                raise VKApiError(-1, f"Сетевая ошибка: {e}", {})

        raise VKApiError(-1, "Превышено количество попыток запроса", {})

    # ==================== High-Level Methods ====================

    async def users_get(self, user_ids: Optional[List[Union[int, str]]] = None, fields: Optional[List[str]] = None) -> List[VKUser]:
        """Fetches user profiles."""
        default_fields = [
            "photo_50", "photo_100", "photo_200", "photo_max_orig",
            "online", "online_mobile", "last_seen", "status", "domain",
            "can_write_private_message"
        ]
        params: Dict[str, Any] = {
            "fields": ",".join(fields or default_fields)
        }
        if user_ids:
            params["user_ids"] = ",".join(str(uid) for uid in user_ids)
            
        resp = await self.request("users.get", params)
        return [VKUser.model_validate(u) for u in resp]

    async def messages_get_conversations(
        self,
        offset: int = 0,
        count: int = 30,
        extended: int = 1,
        filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetches user conversations list with profiles and groups."""
        params: Dict[str, Any] = {
            "offset": offset,
            "count": count,
            "extended": extended,
            "fields": "photo_100,photo_200,online,last_seen"
        }
        if filter:
            params["filter"] = filter
        return await self.request("messages.getConversations", params)

    async def messages_get_conversations_by_id(
        self,
        peer_ids: List[int],
        extended: int = 1
    ) -> Dict[str, Any]:
        """Fetches conversation metadata for specific peer_ids."""
        params = {
            "peer_ids": ",".join(str(p) for p in peer_ids),
            "extended": extended,
            "fields": "photo_100,photo_200,online"
        }
        return await self.request("messages.getConversationsById", params)

    async def messages_get_history(self, peer_id: int, offset: int = 0, count: int = 40, extended: int = 1) -> Dict[str, Any]:
        """Fetches message history for a specific peer (chat/user/group)."""
        params = {
            "peer_id": peer_id,
            "offset": offset,
            "count": count,
            "extended": extended,
            "fields": "photo_100,photo_200,online"
        }
        return await self.request("messages.getHistory", params)

    async def messages_send(self, peer_id: int, message: str, attachment: Optional[str] = None) -> int:
        """Sends a message to a recipient or conversation."""
        random_id = random.randint(1, 2**31 - 1)
        params = {
            "peer_id": peer_id,
            "message": message,
            "random_id": random_id
        }
        if attachment:
            params["attachment"] = attachment
        return await self.request("messages.send", params)

    async def messages_mark_as_read(self, peer_id: int, start_message_id: Optional[int] = None) -> int:
        """Marks incoming messages in conversation as read."""
        params: Dict[str, Any] = {"peer_id": peer_id}
        if start_message_id:
            params["start_message_id"] = start_message_id
        return await self.request("messages.markAsRead", params)

    async def messages_get_long_poll_server(self, lp_version: int = 3, need_pts: int = 0) -> Dict[str, Any]:
        """Fetches Long Poll Server credentials."""
        params = {
            "lp_version": lp_version,
            "need_pts": need_pts
        }
        return await self.request("messages.getLongPollServer", params)


api_client = VKApiClient()
