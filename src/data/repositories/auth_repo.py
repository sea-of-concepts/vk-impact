"""Authentication repository for managing user session state and multi-account storage."""
from typing import Optional, Dict, Any, Union, List, Tuple
from src.core.security import security_manager
from src.core.logger import logger
from src.core.events import event_bus
from src.core.constants import EventType
from src.data.api.auth_web import VKWebAuthEngine
from src.data.api.client import api_client
from src.data.database.db_manager import db_manager
from src.data.repositories.users_repo import users_repo


class AuthRepository:
    """Coordinates authentication flows, multi-account persistence and session switching."""

    def __init__(self, sec_mgr=None):
        self._current_user_id: Optional[int] = None
        self._sec_mgr = sec_mgr

    @property
    def security_mgr(self):
        return self._sec_mgr or security_manager

    @property
    def current_user_id(self) -> Optional[int]:
        return self._current_user_id

    @property
    def is_authenticated(self) -> bool:
        return bool(api_client.access_token)

    def get_accounts(self) -> List[Dict[str, Any]]:
        """Returns all accounts saved in hardware-encrypted storage."""
        return self.security_mgr.load_accounts()

    def get_active_account(self) -> Optional[Dict[str, Any]]:
        """Returns the currently active account."""
        return self.security_mgr.get_active_account()

    async def restore_session(self) -> bool:
        """Attempts to restore the active account session from hardware-encrypted storage."""
        account = self.security_mgr.get_active_account()
        if not account or not account.get("token"):
            return False


        token = account["token"]
        user_id = account.get("id")
        api_client.set_token(token)
        self._current_user_id = user_id

        # Verify token validity by calling users.get
        try:
            users = await api_client.users_get(user_ids=[user_id] if user_id else None)
            if users:
                user = users[0]
                self._current_user_id = user.id
                # Update user details in storage
                account["name"] = user.full_name
                account["avatar_url"] = user.photo_100
                account["impact_style"] = user.impact_style
                self.security_mgr.save_or_update_account(account)

                db_manager.set_user(self._current_user_id)
                await db_manager.init_db()
                logger.info("Session restored for %s (id=%s)", user.full_name, user.id)
                return True
        except Exception as e:
            logger.warning("Saved token validation failed: %s", e)
            # If cookie authentication was used, attempt automatic token refresh
            if account.get("oauths_metod") == "cookie" and account.get("remixsid"):
                try:
                    logger.info("Attempting automatic token refresh via cookies...")
                    refreshed = await VKWebAuthEngine.auth_via_cookies(
                        account.get("remixsid"),
                        p_cookie=account.get("p")
                    )
                    new_token = refreshed["access_token"]
                    api_client.set_token(new_token)
                    account["token"] = new_token
                    
                    users = await api_client.users_get([user_id] if user_id else None)
                    if users:
                        user = users[0]
                        self._current_user_id = user.id
                        account["name"] = user.full_name
                        account["avatar_url"] = user.photo_100
                        account["impact_style"] = user.impact_style
                        self.security_mgr.save_or_update_account(account)

                        db_manager.set_user(self._current_user_id)
                        await db_manager.init_db()
                        logger.info("Token refreshed and session restored for %s", user.full_name)
                        return True
                except Exception as refresh_err:
                    logger.error("Failed to auto-refresh token via cookies: %s", refresh_err)

            self.logout()
            return False

        return False

    async def login_via_cookies(self, cookies_input: Union[str, Dict[str, str]], p_cookie: Optional[str] = None) -> Dict[str, Any]:
        """Exchanges remixsid and p cookies for a permanent API token and saves account."""
        res = await VKWebAuthEngine.auth_via_cookies(cookies_input, p_cookie=p_cookie)
        token = res["access_token"]
        user_id = res.get("user_id", 0)

        api_client.set_token(token)
        users = await api_client.users_get()
        if not users:
            raise ValueError("Токен получен, но не удалось загрузить профиль пользователя")

        user = users[0]
        user_id = user.id
        self._current_user_id = user_id

        cookies = res.get("cookies", {})
        remixsid = cookies.get("remixsid", "")
        p_val = cookies.get("p", "") or (p_cookie.strip() if p_cookie else "")

        account_data = {
            "id": user_id,
            "uid": user_id,
            "name": user.full_name,
            "avatar_url": user.photo_100,
            "impact_style": user.impact_style,
            "oauths_metod": "cookie",
            "token": token,
            "remixsid": remixsid,
            "p": p_val,
            "is_active": True
        }
        self.security_mgr.save_or_update_account(account_data)

        db_manager.set_user(user_id)
        await db_manager.init_db()
        users_repo.clear_cache()

        logger.info("Cookie login successful for user %s (id=%s)", user.full_name, user_id)
        return res

    async def login_via_string_or_token(self, input_str: str) -> Dict[str, Any]:
        """Extracts token from direct string, URL or cookie and validates."""
        cleaned = input_str.strip()

        # If user pasted remixsid / p cookie string
        if "remixsid" in cleaned or ";" in cleaned:
            return await self.login_via_cookies(cleaned)

        token_data = VKWebAuthEngine.extract_token_from_string(cleaned)
        if not token_data:
            raise ValueError("Не удалось распознать токен, ссылку или cookie в введенном тексте")

        token = token_data["access_token"]
        api_client.set_token(token)

        users = await api_client.users_get()
        if not users:
            raise ValueError("Токен недействителен или не имеет доступа к API")

        user = users[0]
        user_id = user.id
        self._current_user_id = user_id

        account_data = {
            "id": user_id,
            "uid": user_id,
            "name": user.full_name,
            "avatar_url": user.photo_100,
            "impact_style": user.impact_style,
            "oauths_metod": "token",
            "token": token,
            "remixsid": "",
            "p": "",
            "is_active": True
        }
        self.security_mgr.save_or_update_account(account_data)

        db_manager.set_user(user_id)
        await db_manager.init_db()
        users_repo.clear_cache()

        logger.info("Token login successful for user %s (id=%s)", user.full_name, user_id)
        return {"access_token": token, "user_id": user_id}

    async def switch_to_account(self, user_id: int) -> bool:
        """Switches the active account to the specified user_id."""
        success = self.security_mgr.set_active_account(user_id)
        if not success:
            return False

        account = self.security_mgr.get_active_account()
        if not account:
            return False

        token = account.get("token", "")
        api_client.set_token(token)
        self._current_user_id = int(user_id)
        db_manager.set_user(self._current_user_id)
        await db_manager.init_db()
        users_repo.clear_cache()

        # Try to validate / refresh
        try:
            users = await api_client.users_get([user_id])
            if users:
                user = users[0]
                account["name"] = user.full_name
                account["avatar_url"] = user.photo_100
                account["impact_style"] = user.impact_style
                self.security_mgr.save_or_update_account(account)
        except Exception as e:
            if account.get("oauths_metod") == "cookie" and account.get("remixsid"):
                try:
                    refreshed = await VKWebAuthEngine.auth_via_cookies(
                        account.get("remixsid"),
                        p_cookie=account.get("p")
                    )
                    api_client.set_token(refreshed["access_token"])
                    account["token"] = refreshed["access_token"]
                    self.security_mgr.save_or_update_account(account)
                except Exception as r_err:
                    logger.error("Failed refreshing token on account switch: %s", r_err)

        event_bus.emit(EventType.AUTH_SUCCESS, user_id=self._current_user_id)
        return True

    async def delete_account(self, user_id: int) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Deletes account with user_id.
        Returns (action, remaining_accounts):
        - 'auth': 0 accounts left, user logged out.
        - 'switched': 1 account left, automatically switched to it.
        - 'select': >1 accounts left, navigate to account selection menu.
        """
        accounts = self.security_mgr.load_accounts()
        initial_count = len(accounts)

        remaining = self.security_mgr.remove_account(user_id)
        users_repo.clear_cache()

        if initial_count <= 1 or not remaining:
            self.logout()
            return ("auth", remaining)
        elif initial_count == 2 or len(remaining) == 1:
            next_user_id = remaining[0]["id"]
            await self.switch_to_account(next_user_id)
            return ("switched", remaining)
        else:
            # More than 2 accounts initially -> user must pick from remaining
            api_client.set_token("")
            self._current_user_id = None
            return ("select", remaining)

    def logout(self) -> None:
        """Clears active token and current user."""
        api_client.set_token("")
        self._current_user_id = None
        users_repo.clear_cache()
        self.security_mgr.clear_session()



auth_repo = AuthRepository()
