"""Headless VK OAuth Web Flow Parser without embedded browser."""
import urllib.parse
from typing import Optional, Dict, Any, Tuple
import aiohttp
from bs4 import BeautifulSoup
from src.core.config import config
from src.core.logger import logger
from src.data.api.http_client import create_http_session


class VKWebOAuthParser:
    """Parses and automates VK OAuth web flow headlessly."""

    def __init__(self, client_id: Optional[str] = None, scope: Optional[int] = None):
        self.client_id = client_id or config.DEFAULT_CLIENT_ID
        self.scope = scope or config.DEFAULT_SCOPE
        self.cookie_jar = aiohttp.CookieJar(unsafe=True)
        self._auth_state: Dict[str, Any] = {}

    def _get_session(self) -> aiohttp.ClientSession:
        return create_http_session(
            headers={"User-Agent": config.WEB_USER_AGENT},
            cookie_jar=self.cookie_jar,
            timeout_seconds=20.0
        )

    @staticmethod
    def _extract_token_from_url(url: str) -> Optional[Dict[str, Any]]:
        """Extracts access_token and user_id from redirect URL fragment."""
        if "#" not in url:
            return None
        fragment = url.split("#", 1)[1]
        params = urllib.parse.parse_qs(fragment)
        if "access_token" in params:
            token = params["access_token"][0]
            user_id = int(params.get("user_id", [0])[0])
            expires_in = int(params.get("expires_in", [0])[0])
            return {
                "access_token": token,
                "user_id": user_id,
                "expires_in": expires_in,
                "email": params.get("email", [None])[0]
            }
        return None

    async def start_web_auth(
        self,
        login: str,
        password: str,
        captcha_sid: Optional[str] = None,
        captcha_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Starts the web auth flow:
        1. Loads initial OAuth page
        2. Parses hidden form fields
        3. Posts credentials
        4. Follows redirects or handles 2FA/Permissions/Captcha
        """
        auth_url = (
            f"https://oauth.vk.com/authorize?"
            f"client_id={self.client_id}&"
            f"redirect_uri=https://oauth.vk.com/blank.html&"
            f"display=mobile&"
            f"scope={self.scope}&"
            f"response_type=token&"
            f"v={config.VK_API_VERSION}&"
            f"revoke=1"
        )

        async with self._get_session() as session:
            # 1. GET initial authorization page
            async with session.get(auth_url) as resp:
                # Check if already authenticated via cookies
                token_data = self._extract_token_from_url(str(resp.url))
                if token_data:
                    return token_data

                html = await resp.text()

            # 2. Parse login form
            soup = BeautifulSoup(html, "html.parser")
            form = soup.find("form")
            if not form:
                # Check if there's an error on page
                err_box = soup.find("div", {"class": "error_box"}) or soup.find("div", {"class": "service_msg_warning"})
                err_text = err_box.get_text(strip=True) if err_box else "Не удалось найти форму входа"
                raise RuntimeError(err_text)

            action = form.get("action", "")
            if not action.startswith("http"):
                action = urllib.parse.urljoin(auth_url, action)

            # Collect form fields
            form_data = {}
            for input_tag in form.find_all("input"):
                name = input_tag.get("name")
                if name:
                    form_data[name] = input_tag.get("value", "")

            # Fill in user credentials
            form_data["email"] = login
            form_data["pass"] = password
            if captcha_sid and captcha_key:
                form_data["captcha_sid"] = captcha_sid
                form_data["captcha_key"] = captcha_key

            # 3. POST credentials
            async with session.post(action, data=form_data, allow_redirects=True) as post_resp:
                final_url = str(post_resp.url)
                token_data = self._extract_token_from_url(final_url)
                if token_data:
                    return token_data

                post_html = await post_resp.text()

            # 4. Analyze response for 2FA, Captcha, Consent, or Errors
            return await self._handle_post_response(session, final_url, post_html)

    async def _handle_post_response(
        self,
        session: aiohttp.ClientSession,
        current_url: str,
        html: str
    ) -> Dict[str, Any]:
        """Analyzes post-login HTML for 2FA, permissions consent, or captcha."""
        soup = BeautifulSoup(html, "html.parser")

        # Check for captcha
        captcha_img_tag = soup.find("img", {"class": "captcha_img"}) or soup.find("img", src=lambda s: s and "captcha.php" in s)
        if captcha_img_tag:
            captcha_sid_tag = soup.find("input", {"name": "captcha_sid"})
            captcha_sid = captcha_sid_tag.get("value") if captcha_sid_tag else ""
            captcha_url = captcha_img_tag.get("src", "")
            if not captcha_url.startswith("http"):
                captcha_url = urllib.parse.urljoin(current_url, captcha_url)

            from src.data.api.auth import VKAuthError
            raise VKAuthError(
                message="Требуется ввод капчи",
                error_type="captcha_required",
                extra={"captcha_sid": captcha_sid, "captcha_img": captcha_url}
            )

        # Check for 2FA / SMS confirmation
        if "act=authcheck" in current_url or soup.find("input", {"name": "code"}):
            form = soup.find("form")
            action = form.get("action", "") if form else ""
            if not action.startswith("http"):
                action = urllib.parse.urljoin(current_url, action)

            form_data = {}
            if form:
                for inp in form.find_all("input"):
                    n = inp.get("name")
                    if n:
                        form_data[n] = inp.get("value", "")

            self._auth_state = {
                "action": action,
                "form_data": form_data,
                "current_url": current_url
            }

            from src.data.api.auth import VKAuthError
            raise VKAuthError(
                message="Требуется код подтверждения (2FA / SMS)",
                error_type="2fa_required",
                extra={"state": self._auth_state}
            )

        # Check for Permissions Grant (Consent page: "Разрешить доступ")
        grant_form = soup.find("form", action=lambda a: a and "grant_access" in a) or soup.find("form")
        if grant_form and ("grant_access" in grant_form.get("action", "") or "oauth.vk.com/authorize" in current_url):
            action = grant_form.get("action", "")
            if not action.startswith("http"):
                action = urllib.parse.urljoin(current_url, action)

            data = {}
            for inp in grant_form.find_all("input"):
                n = inp.get("name")
                if n:
                    data[n] = inp.get("value", "")

            # Submit consent
            async with session.post(action, data=data, allow_redirects=True) as grant_resp:
                token_data = self._extract_token_from_url(str(grant_resp.url))
                if token_data:
                    return token_data

        # Check for error text in HTML
        err_elem = (
            soup.find("div", {"class": "service_msg_warning"}) or
            soup.find("div", {"class": "error_box"}) or
            soup.find("div", {"id": "message"}) or
            soup.find("div", {"class": "vkc__AuthRoot__error"})
        )
        if err_elem:
            msg = err_elem.get_text(strip=True)
            from src.data.api.auth import VKAuthError
            raise VKAuthError(f"Ошибка входа: {msg}", error_type="invalid_credentials")

        # Generic failure
        from src.data.api.auth import VKAuthError
        raise VKAuthError("Не удалось получить токен доступа. Проверьте логин и пароль.", error_type="unknown")

    async def submit_2fa_code(self, code: str) -> Dict[str, Any]:
        """Submits 2FA confirmation code for pending web auth."""
        if not self._auth_state:
            raise RuntimeError("Нет активной сессии двухфакторной аутентификации")

        action = self._auth_state.get("action", "")
        form_data = dict(self._auth_state.get("form_data", {}))
        form_data["code"] = code.strip()

        async with self._get_session() as session:
            async with session.post(action, data=form_data, allow_redirects=True) as resp:
                token_data = self._extract_token_from_url(str(resp.url))
                if token_data:
                    return token_data
                html = await resp.text()
                return await self._handle_post_response(session, str(resp.url), html)
