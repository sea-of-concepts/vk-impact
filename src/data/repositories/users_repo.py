"""Users repository managing local SQLite caching with 12-hour expiration TTL."""
import time
from typing import Dict, Any, Optional, List
from src.data.database.db_manager import db_manager
from src.data.api.client import api_client
from src.core.logger import logger


class UsersRepository:
    """Provides user profiles cached locally with a 12-hour TTL."""

    def __init__(self):
        self._memory_cache: Dict[int, Dict[str, Any]] = {}
        self.TTL_SECONDS = 12 * 3600  # 12 hours

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves user info:
        1. Checks memory cache.
        2. Checks SQLite local cache.
        3. If missing or updated > 12h ago, fetches fresh via users.get and updates SQLite.
        """
        now = time.time()

        # 1. Memory cache check
        if user_id in self._memory_cache:
            u = self._memory_cache[user_id]
            if (now - u.get("updated_at", 0)) < self.TTL_SECONDS:
                return u

        # 2. SQLite cache check
        db_user = await db_manager.get_cached_user(user_id)
        if db_user:
            self._memory_cache[user_id] = db_user
            if (now - db_user.get("updated_at", 0)) < self.TTL_SECONDS:
                return db_user

        # 3. Fetch from VK API (users.get)
        try:
            users = await api_client.users_get(user_ids=[user_id])
            if users:
                u_obj = users[0]
                user_dict = {
                    "id": u_obj.id,
                    "first_name": u_obj.first_name,
                    "last_name": u_obj.last_name,
                    "photo_100": u_obj.photo_100 or "",
                    "photo_200": u_obj.photo_200 or "",
                    "online": int(u_obj.online),
                    "impact_style": u_obj.impact_style,
                    "updated_at": int(now)
                }
                self._memory_cache[user_id] = user_dict
                await db_manager.save_cached_users([user_dict])
                return user_dict
        except Exception as e:
            logger.warning("Failed to fetch user %s from API: %s", user_id, e)

        return db_user

    async def get_user_impact_style(self, user_id: int) -> str:
        """Returns the impact_style for a user (e.g. 'zephyr') or empty string."""
        if user_id <= 0:
            return ""
        user = await self.get_user(user_id)
        return user.get("impact_style", "") if user else ""

    async def get_user_name_prefix(self, user_id: int) -> str:
        """Returns 'First LastInitial.: ' prefix for messages in chat."""
        if user_id <= 0:
            return ""
        user = await self.get_user(user_id)
        if not user:
            return ""
        fn = user.get("first_name", "").strip()
        ln = user.get("last_name", "").strip()
        initial = f" {ln[0]}." if ln else ""
        return f"{fn}{initial}: ".strip() + " "

    def clear_cache(self) -> None:
        """Clears the in-memory user cache."""
        self._memory_cache.clear()


users_repo = UsersRepository()

