"""Authentication repository for managing user session state."""
from typing import Optional, Dict, Any, Union
from src.core.security import security_manager
from src.core.logger import logger
from src.data.api.auth_web import VKWebAuthEngine
from src.data.api.client import api_client


class AuthRepository:
    """Coordinates authentication flows, token persistence and validation."""

    def __init__(self):
        self._current_user_id: Optional[int] = None

    @property
    def current_user_id(self) -> Optional[int]:
        return self._current_user_id

    @property
    def is_authenticated(self) -> bool:
        return bool(api_client.access_token)

    async def restore_session(self) -> bool:
        """Attempts to restore a saved session from encrypted storage."""
        session = security_manager.load_session()
        if not session or "access_token" not in session:
            return False
            
        token = session["access_token"]
        user_id = session.get("user_id")
        api_client.set_token(token)
        self._current_user_id = user_id

        # Verify token validity by calling users.get
        try:
            users = await api_client.users_get(user_ids=[user_id] if user_id else None)
            if users:
                self._current_user_id = users[0].id
                logger.info("Session restored for %s (id=%s)", users[0].full_name, users[0].id)
                return True
        except Exception as e:
            logger.warning("Saved token is invalid: %s", e)
            self.logout()
            return False
        return False

    async def login_via_cookies(self, cookies_input: Union[str, Dict[str, str]], p_cookie: Optional[str] = None) -> Dict[str, Any]:
        """Exchanges remixsid and p cookies for a permanent API token and saves session."""
        res = await VKWebAuthEngine.auth_via_cookies(cookies_input, p_cookie=p_cookie)
        token = res["access_token"]
        user_id = res.get("user_id", 0)

        api_client.set_token(token)
        # Fetch user info to verify
        users = await api_client.users_get()
        if not users:
            raise ValueError("Токен получен, но не удалось загрузить профиль пользователя")

        user_id = users[0].id
        self._current_user_id = user_id
        security_manager.save_session(token=token, user_id=user_id, extra_data=res)
        logger.info("Cookie login successful for user %s (id=%s)", users[0].full_name, user_id)
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

        user_id = users[0].id
        self._current_user_id = user_id
        security_manager.save_session(token=token, user_id=user_id, extra_data=token_data)
        logger.info("Token login successful for user %s (id=%s)", users[0].full_name, user_id)
        return {"access_token": token, "user_id": user_id}

    def logout(self) -> None:
        """Clears active token and deletes stored session."""
        api_client.set_token("")
        self._current_user_id = None
        security_manager.clear_session()


auth_repo = AuthRepository()
