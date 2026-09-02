"""User Long Poll listener for real-time VK events."""
import asyncio
from typing import Optional, Dict, Any, Callable
import aiohttp
from src.core.logger import logger
from src.core.events import event_bus
from src.core.constants import EventType
from src.data.api.client import VKApiClient


from src.data.api.http_client import create_http_session


class VKLongPollService:
    """Listens for real-time events from VK User Long Poll server."""

    def __init__(self, api_client: VKApiClient):
        self.api_client = api_client
        self._is_running = False
        self._server: Optional[str] = None
        self._key: Optional[str] = None
        self._ts: Optional[int] = None
        self._pts: Optional[int] = None
        self._task: Optional[asyncio.Task] = None

    async def _update_server_data(self) -> None:
        """Requests fresh Long Poll server credentials from VK API."""
        data = await self.api_client.messages_get_long_poll_server(lp_version=3, need_pts=0)
        self._server = data.get("server")
        self._key = data.get("key")
        self._ts = data.get("ts")
        self._pts = data.get("pts")
        logger.info("Long Poll server credentials updated (ts=%s)", self._ts)

    async def start(self) -> None:
        """Starts the Long Poll listener loop."""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._listen_loop())
        logger.info("Long Poll listener started.")

    async def stop(self) -> None:
        """Stops the Long Poll listener."""
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Long Poll listener stopped.")

    async def _listen_loop(self) -> None:
        """Main listening loop polling the Long Poll server."""
        async with create_http_session(timeout_seconds=40.0) as session:
            while self._is_running:
                try:
                    if not self._server or not self._key or self._ts is None:
                        await self._update_server_data()

                    url = f"https://{self._server}"
                    params = {
                        "act": "a_check",
                        "key": self._key,
                        "ts": str(self._ts),
                        "wait": "25",
                        "mode": "2",
                        "version": "3"
                    }

                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=35)) as resp:
                        data = await resp.json()

                    if "failed" in data:
                        code = data.get("failed")
                        if code == 1:
                            # Update ts
                            self._ts = data.get("ts")
                        elif code in (2, 3):
                            # Key expired or new server needed
                            await self._update_server_data()
                        continue

                    # Update ts for next poll
                    self._ts = data.get("ts", self._ts)
                    updates = data.get("updates", [])

                    for update in updates:
                        await self._process_update(update)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning("Long Poll error: %s. Retrying in 3s...", e)
                    await asyncio.sleep(3)

    async def _process_update(self, update: list) -> None:
        """Dispatches Long Poll update events to the EventBus."""
        if not update or not isinstance(update, list):
            return

        event_code = update[0]
        from src.core.log_collector import log_collector

        # 4 = New message: [4, message_id, flags, peer_id, timestamp, text, extra/attachments, random_id, cmid]
        if event_code == 4:
            msg_id = update[1]
            flags = update[2]
            peer_id = update[3]
            timestamp = update[4]
            text = update[5] if len(update) > 5 else ""
            extra = update[6] if len(update) > 6 and isinstance(update[6], dict) else {}
            random_id = update[7] if len(update) > 7 else 0
            cmid = update[8] if len(update) > 8 else extra.get("conversation_message_id", 0)

            is_out = bool(flags & 2)
            try:
                from_id = int(extra.get("from", peer_id if not is_out else 0))
            except Exception:
                from_id = peer_id if not is_out else 0

            # Log with full raw update data for inspector
            log_collector.log_longpoll(
                "New Message",
                f"peer={peer_id}, text='{text[:25]}'",
                raw_data=update
            )

            event_bus.emit(
                EventType.NEW_MESSAGE,
                message_id=msg_id,
                peer_id=peer_id,
                from_id=from_id,
                text=text,
                timestamp=timestamp,
                is_out=is_out,
                attachments=extra,
                conversation_message_id=cmid
            )
            event_bus.emit(EventType.DIALOG_UPDATED, peer_id=peer_id)

        # 6 or 7 = Incoming/Outgoing message read
        elif event_code in (6, 7):
            peer_id = update[1]
            local_id = update[2]
            log_collector.log_longpoll("Message Read", f"peer={peer_id}, id={local_id}")
            event_bus.emit(EventType.MESSAGE_READ, peer_id=peer_id, message_id=local_id)

        # 61, 62 = User started typing in dialog / chat
        elif event_code in (61, 62):
            user_id = update[1]
            log_collector.log_longpoll("User Typing", f"user={user_id}")
            event_bus.emit(EventType.USER_TYPING, user_id=user_id)
