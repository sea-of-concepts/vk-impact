"""VK Web Client Emulation and Token Engine."""
import re
import urllib.parse
import webbrowser
from typing import Optional, Dict, Any, Union
import httpx
from bs4 import BeautifulSoup
from src.core.config import config
from src.core.logger import logger
from src.data.api.http_client import create_http_session


class VKWebAuthEngine:
    """
    Emulates VK Web Client authentication:
    1. Direct Web Access Token acquisition via login.vk.com/?act=web_token using `remixsid` and `p`.
    2. One-click token acquisition via default system browser.
    3. Smart token/URL/cookie extraction.
    """

    DEFAULT_CLIENT_ID = "2685278"  # Kate Mobile (perpetual token)
    DEFAULT_WEB_APP_ID = "6287487"  # VK Web / Desktop
    DEFAULT_SCOPE = 1073741823

    @classmethod
    def get_browser_oauth_url(cls, client_id: Optional[str] = None) -> str:
        """Returns OAuth URL to open in system browser."""
        params = {
            "client_id": client_id or cls.DEFAULT_CLIENT_ID,
            "scope": str(cls.DEFAULT_SCOPE),
            "redirect_uri": "https://oauth.vk.com/blank.html",
            "display": "page",
            "response_type": "token",
            "v": config.VK_API_VERSION,
            "revoke": "1"
        }
        return f"https://oauth.vk.com/authorize?{urllib.parse.urlencode(params)}"

    @classmethod
    def open_oauth_in_browser(cls, client_id: Optional[str] = None) -> None:
        """Opens official VK OAuth in system browser."""
        url = cls.get_browser_oauth_url(client_id)
        logger.info("Opening OAuth URL in system browser: %s", url)
        webbrowser.open(url)

    @classmethod
    def parse_cookie_string(cls, cookie_input: str) -> Dict[str, str]:
        """Parses a raw cookie string or key-values into a normalized dictionary."""
        cookies = {}
        for item in cookie_input.replace("\n", ";").split(";"):
            item = item.strip()
            if not item:
                continue
            if "=" in item:
                k, v = item.split("=", 1)
                cookies[k.strip()] = v.strip()
            else:
                cookies["remixsid"] = item
        return cookies

    @classmethod
    def extract_token_from_string(cls, raw_input: str) -> Optional[Dict[str, Any]]:
        """
        Smart parser extracting token, user_id and params from:
        - Direct token: 'vk1.a.xxxx...'
        - Full URL: 'https://oauth.vk.com/blank.html#access_token=...&user_id=...'
        - Key-value string: 'access_token=...&user_id=...'
        """
        if not raw_input:
            return None
        text = raw_input.strip()

        # Case 1: Full URL with fragment or query
        if "access_token=" in text:
            fragment = text.split("#", 1)[-1] if "#" in text else text.split("?", 1)[-1]
            params = urllib.parse.parse_qs(fragment)
            if "access_token" in params:
                token = params["access_token"][0]
                user_id = int(params.get("user_id", [0])[0])
                expires_in = int(params.get("expires_in", [0])[0])
                return {
                    "access_token": token,
                    "user_id": user_id,
                    "expires_in": expires_in,
                    "auth_type": "url"
                }

        # Case 2: Pure token starting with 'vk1.a.' or standard length hex/base64 token
        if text.startswith("vk1.a.") or (len(text) >= 64 and not text.startswith("http") and "=" not in text and ";" not in text):
            return {
                "access_token": text,
                "user_id": 0,
                "expires_in": 0,
                "auth_type": "direct_token"
            }

        return None

    @classmethod
    async def get_web_access_token(
        cls,
        remixsid: Optional[str] = None,
        cookie_p: Optional[str] = None,
        app_id: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Получение веб access_token через login.vk.com/?act=web_token по сессионным куки remixsid и p.
        """
        sid = (remixsid or "").strip()
        p = (cookie_p or "").strip()
        ua = user_agent or config.WEB_USER_AGENT
        aid = app_id or config.VK_WEB_APP_ID or cls.DEFAULT_WEB_APP_ID

        if not sid:
            raise ValueError("Cookie 'remixsid' не найдена в переданных параметрах")

        url = "https://login.vk.com/?act=web_token"
        headers = {
            "User-Agent": ua,
            "Origin": "https://vk.com",
            "Referer": "https://vk.com/",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/plain, */*",
        }
        cookies = {"remixsid": sid}
        if p:
            cookies["p"] = p

        payload = {
            "version": "1",
            "app_id": str(aid),
        }

        async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
            response = await client.post(url, headers=headers, cookies=cookies, data=payload)
            response.raise_for_status()
            json_data = response.json()

            if json_data.get("type") == "error":
                error_info = json_data.get("error_info", "Неизвестная ошибка")
                raise RuntimeError(f"Ошибка авторизации login.vk.com: {error_info}")

            data_dict = json_data.get("data", {})
            token = data_dict.get("access_token")
            user_id = data_dict.get("user_id", 0)

            if not token:
                raise ValueError(f"Токен не найден в ответе сервера: {json_data}")

            logger.info("Web access_token successfully obtained for user_id=%s", user_id)
            return {
                "access_token": token,
                "user_id": user_id,
                "expires_in": data_dict.get("expires_in", 0),
                "cookies": cookies
            }

    @classmethod
    async def auth_via_cookies(
        cls,
        cookies_input: Union[str, Dict[str, str]],
        p_cookie: Optional[str] = None,
        app_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Универсальный вход по cookie (remixsid и p) через act=web_token.
        """
        if isinstance(cookies_input, str):
            cookies = cls.parse_cookie_string(cookies_input)
        else:
            cookies = dict(cookies_input)

        if p_cookie and p_cookie.strip():
            cookies["p"] = p_cookie.strip()

        remixsid = cookies.get("remixsid", "")
        p_val = cookies.get("p", "")

        return await cls.get_web_access_token(
            remixsid=remixsid,
            cookie_p=p_val,
            app_id=app_id
        )
