"""VK API Authentication Handler supporting Direct Auth and Web Flow Parsing."""
import urllib.parse
from typing import Optional, Dict, Any
import aiohttp
from src.core.config import config
from src.core.logger import logger
from src.data.api.http_client import create_http_session
from src.data.api.auth_web_parser import VKWebOAuthParser


class VKAuthError(Exception):
    """Raised when authentication fails."""
    def __init__(self, message: str, error_type: str = "general", extra: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_type = error_type
        self.extra = extra or {}


class VKAuth:
    """Handles VK authentication flows (Direct Auth and Headless Web Flow)."""
    
    _web_parser: Optional[VKWebOAuthParser] = None

    @staticmethod
    def get_oauth_url(client_id: Optional[str] = None, scope: Optional[int] = None) -> str:
        """Generates OAuth 2.0 Implicit Flow URL."""
        params = {
            "client_id": client_id or config.DEFAULT_CLIENT_ID,
            "display": "page",
            "redirect_uri": "https://oauth.vk.com/blank.html",
            "scope": str(scope or config.DEFAULT_SCOPE),
            "response_type": "token",
            "v": config.VK_API_VERSION,
            "revoke": "1"
        }
        return f"{config.VK_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    @classmethod
    async def direct_auth(
        cls,
        login: str,
        password: str,
        code_2fa: Optional[str] = None,
        captcha_sid: Optional[str] = None,
        captcha_key: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Performs direct username/password authentication against VK OAuth server.
        Uses SSL-configured session and official client credentials.
        """
        c_id = client_id or config.DEFAULT_CLIENT_ID
        c_secret = client_secret or config.DEFAULT_CLIENT_SECRET
        
        params = {
            "grant_type": "password",
            "client_id": c_id,
            "client_secret": c_secret,
            "username": login,
            "password": password,
            "scope": str(config.DEFAULT_SCOPE),
            "v": config.VK_API_VERSION,
            "2fa_supported": "1"
        }
        
        if code_2fa:
            params["code"] = code_2fa
        if captcha_sid and captcha_key:
            params["captcha_sid"] = captcha_sid
            params["captcha_key"] = captcha_key

        async with create_http_session(timeout_seconds=15.0) as session:
            try:
                async with session.get(config.VK_OAUTH_URL, params=params) as resp:
                    data = await resp.json(content_type=None)
                    
                    if "error" in data:
                        err = data.get("error")
                        err_desc = data.get("error_description", "Неизвестная ошибка")
                        
                        if err == "need_validation":
                            # 2FA required
                            validation_type = data.get("validation_type", "2fa_sms")
                            phone_mask = data.get("phone_mask", "")
                            validation_sid = data.get("validation_sid", "")
                            msg = f"Требуется код подтверждения"
                            if phone_mask:
                                msg += f" ({phone_mask})"
                            raise VKAuthError(
                                message=msg,
                                error_type="2fa_required",
                                extra={"validation_type": validation_type, "phone_mask": phone_mask, "validation_sid": validation_sid}
                            )
                        elif err == "need_captcha":
                            # Captcha required
                            c_sid = data.get("captcha_sid")
                            c_img = data.get("captcha_img")
                            raise VKAuthError(
                                message="Требуется ввод капчи",
                                error_type="captcha_required",
                                extra={"captcha_sid": c_sid, "captcha_img": c_img}
                            )
                        elif err == "invalid_client":
                            # Fallback to headless web auth if direct auth client is rejected
                            logger.info("Direct auth client rejected, falling back to Web OAuth parser...")
                            cls._web_parser = VKWebOAuthParser(client_id=c_id)
                            return await cls._web_parser.start_web_auth(
                                login=login,
                                password=password,
                                captcha_sid=captcha_sid,
                                captcha_key=captcha_key
                            )
                        else:
                            raise VKAuthError(
                                message=f"Ошибка входа: {err_desc}",
                                error_type="invalid_credentials",
                                extra=data
                            )
                    
                    # Successful auth
                    access_token = data.get("access_token")
                    user_id = data.get("user_id")
                    logger.info("Direct auth successful for user_id=%s", user_id)
                    return {
                        "access_token": access_token,
                        "user_id": int(user_id) if user_id else 0,
                        "expires_in": data.get("expires_in", 0),
                        "email": data.get("email"),
                    }
            except aiohttp.ClientError as e:
                logger.error("Network error during auth: %s", e)
                raise VKAuthError(f"Сетевая ошибка при подключении: {e}", error_type="network_error")

    @classmethod
    async def submit_web_2fa(cls, code: str) -> Dict[str, Any]:
        """Submits 2FA code to pending web parser."""
        if not cls._web_parser:
            raise VKAuthError("Нет активного веб-сеанса авторизации", error_type="general")
        return await cls._web_parser.submit_2fa_code(code)
