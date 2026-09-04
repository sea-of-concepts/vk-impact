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
                    
                    if response.status != 200:
                        raise VKApiError(-1, f"HTTP {response.status}", {})

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
                    return data.get("response", data)
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

    async def fetch_impact_extra(self, user_ids: Optional[List[Union[int, str]]] = None) -> Dict[int, Dict[str, Any]]:
        """
        Sends simultaneous request to https://zephyrianna.pythonanywhere.com/users.get with user_ids.
        Expects: {"response": [{"id": 708902696, "impact_extra": {"impact_style": "zephyr"}}]}
        Returns mapping: user_id -> impact_extra dict.
        """
        if not user_ids:
            return {}
        try:
            session = await self._get_session()
            payload = {
                "user_ids": ",".join(str(uid) for uid in user_ids)
            }
            async with session.post(
                "https://zephyrianna.pythonanywhere.com/users.get",
                data=payload,
                timeout=aiohttp.ClientTimeout(total=4)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get("response", data)
                    if isinstance(items, list):
                        mapping = {}
                        for item in items:
                            if isinstance(item, dict) and "id" in item:
                                uid = int(item["id"])
                                extra = item.get("impact_extra")
                                if isinstance(extra, dict):
                                    mapping[uid] = extra
                                elif item.get("impact_style"):
                                    mapping[uid] = {"impact_style": item["impact_style"]}
                        return mapping
        except Exception as e:
            logger.debug("zephyrianna fetch_impact_extra failed: %s", e)
        return {}

    async def users_get(self, user_ids: Optional[List[Union[int, str]]] = None, fields: Optional[List[str]] = None) -> List[VKUser]:
        """Fetches user profiles from official VK API and merges impact_extra from zephyrianna."""
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
            
        vk_task = self.request("users.get", params)
        impact_task = self.fetch_impact_extra(user_ids)
        vk_resp, impact_map = await asyncio.gather(vk_task, impact_task, return_exceptions=False)

        users = []
        for u in vk_resp:
            uid = u.get("id")
            if uid in impact_map:
                u["impact_extra"] = impact_map[uid]
            elif uid == 708902696 and not u.get("impact_extra"):
                u["impact_extra"] = {"impact_style": "zephyr"}
            users.append(VKUser.model_validate(u))
        return users

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

    async def messages_get_items(
        self,
        filter: str = "all",
        start_from: str = "conversations_0,channels_0_0",
        target_count: int = 20,
        extended: int = 1,
        group_id: int = 0,
        fields: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetches conversations and channels using messages.getItems."""
        default_fields = (
            "id,first_name,first_name_gen,first_name_acc,first_name_ins,first_name_dat,"
            "last_name,last_name_gen,last_name_acc,last_name_ins,sex,has_photo,photo_id,"
            "photo_50,photo_100,photo_200,contact_name,occupation,bdate,city,screen_name,"
            "online_info,verified,blacklisted,blacklisted_by_me,language,can_call,"
            "can_write_private_message,can_send_friend_request,can_invite_to_chats,"
            "friend_status,followers_count,profile_type,contacts,employee_mark,"
            "employee_working_state,is_service_account,image_status,photo_base,"
            "educational_profile,edu_roles,is_followers_mode_on,name,type,members_count,"
            "member_status,is_closed,can_message,deactivated,activity,ban_info,"
            "is_messages_blocked,can_send_notify,can_post_donut,site,reposts_disabled,"
            "description,action_button,menu,role,unread_count,wall,can_manage,"
            "disallow_manage_reason,age_limits,warning_notification"
        )
        params = {
            "filter": filter,
            "start_from": start_from or "conversations_0,channels_0_0",
            "extended": extended,
            "target_count": target_count,
            "group_id": group_id,
            "fields": fields or default_fields
        }
        return await self.request("messages.getItems", params)

    async def channels_get_history(
        self,
        channel_id: int,
        count: int = 40,
        offset: int = 0,
        start_cmid: Optional[int] = None,
        extended: int = 1,
        fields: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetches channel message history using channels.getHistory."""
        default_fields = (
            "id,first_name,first_name_gen,first_name_acc,first_name_ins,first_name_dat,"
            "last_name,last_name_gen,last_name_acc,last_name_ins,sex,has_photo,photo_id,"
            "photo_50,photo_100,photo_200,contact_name,occupation,bdate,city,screen_name,"
            "online_info,verified,blacklisted,blacklisted_by_me,language,can_call,"
            "can_write_private_message,can_send_friend_request,can_invite_to_chats,"
            "friend_status,followers_count,profile_type,contacts,employee_mark,"
            "employee_working_state,is_service_account,image_status,photo_base,"
            "educational_profile,edu_roles,is_followers_mode_on,name,type,members_count,"
            "member_status,is_closed,can_message,deactivated,activity,ban_info,"
            "is_messages_blocked,can_send_notify,can_post_donut,site,reposts_disabled,"
            "description,action_button,menu,role,unread_count,wall,can_manage,"
            "disallow_manage_reason,age_limits,warning_notification"
        )
        if start_cmid is None:
            start_cmid = 1_000_000_000

        params: Dict[str, Any] = {
            "channel_id": channel_id,
            "count": count,
            "offset": offset,
            "start_cmid": start_cmid,
            "extended": extended,
            "fields": fields or default_fields
        }
        return await self.request("channels.getHistory", params)

    async def channels_mark_as_read(self, channel_id: int, last_read_cmid: int) -> int:
        """Marks channel messages as read using channels.markAsRead."""
        params: Dict[str, Any] = {
            "channel_id": channel_id,
            "last_read_cmid": last_read_cmid
        }
        return await self.request("channels.markAsRead", params)

    async def channels_set_notification_mode(self, channel_id: int, mode: str) -> int:
        """Sets channel notification mode ('enabled' or 'disabled')."""
        params: Dict[str, Any] = {
            "channel_id": channel_id,
            "mode": mode
        }
        return await self.request("channels.setNotificationMode", params)

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
        else:
            params["start_message_id"] = 0
        try:
            return await self.request("messages.markAsRead", params)
        except Exception:
            return 0

    async def messages_get_long_poll_server(self, lp_version: int = 3, need_pts: int = 0) -> Dict[str, Any]:
        """Fetches Long Poll Server credentials."""
        params = {
            "lp_version": lp_version,
            "need_pts": need_pts
        }
        return await self.request("messages.getLongPollServer", params)


api_client = VKApiClient()
