"""Unit tests for authentication flows and web parser."""
import os
import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.api.auth_web_parser import VKWebOAuthParser
from src.data.api.auth_web import VKWebAuthEngine
from src.data.api.auth import VKAuth, VKAuthError
from src.data.api.http_client import create_http_session


def test_token_extraction():
    """Tests extraction of access_token from OAuth redirect URL."""
    redirect_url = "https://oauth.vk.com/blank.html#access_token=vk1.a.secret1234567890&expires_in=0&user_id=123456&email=test@example.com"
    data = VKWebOAuthParser._extract_token_from_url(redirect_url)
    assert data is not None
    assert data["access_token"] == "vk1.a.secret1234567890"
    assert data["user_id"] == 123456
    assert data["expires_in"] == 0
    assert data["email"] == "test@example.com"

    # Invalid URL without fragment
    assert VKWebOAuthParser._extract_token_from_url("https://oauth.vk.com/blank.html") is None


def test_smart_string_parser():
    """Tests VKWebAuthEngine smart string parser for tokens, URLs and cookies."""
    # Direct token
    t1 = "vk1.a.abcdefghijklmnopqrstuvwxyz1234567890_ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    res1 = VKWebAuthEngine.extract_token_from_string(t1)
    assert res1 is not None
    assert res1["access_token"] == t1

    # Full redirect URL
    url = "https://oauth.vk.com/blank.html#access_token=vk1.a.testtoken999&user_id=777&expires_in=0"
    res2 = VKWebAuthEngine.extract_token_from_string(url)
    assert res2 is not None
    assert res2["access_token"] == "vk1.a.testtoken999"
    assert res2["user_id"] == 777


def test_oauth_url_generation():
    """Tests OAuth URL format generation."""
    url = VKAuth.get_oauth_url()
    assert "oauth.vk.com/authorize" in url
    assert "response_type=token" in url
    assert "redirect_uri" in url


async def test_ssl_http_connection():
    """Tests that HTTP session with custom SSL connector connects without SSL errors."""
    async with create_http_session(timeout_seconds=5.0) as session:
        async with session.get("https://oauth.vk.com/token") as resp:
            # We expect a 401 or valid response without SSLCertVerificationError
            assert resp.status in (200, 400, 401)
            data = await resp.json(content_type=None)
            assert "error" in data


def test_cookie_string_parsing():
    """Tests parsing raw cookie string."""
    raw = "remixsid=abcdef123456; p=secret_p_value; remixmid=99999"
    cookies = VKWebAuthEngine.parse_cookie_string(raw)
    assert cookies["remixsid"] == "abcdef123456"
    assert cookies["p"] == "secret_p_value"
    assert cookies["remixmid"] == "99999"


async def test_get_web_access_token_endpoint():
    """Tests that act=web_token handles invalid credentials with error JSON and no SSL failure."""
    try:
        await VKWebAuthEngine.get_web_access_token(remixsid="invalid_sid_test", cookie_p="test_p")
    except RuntimeError as e:
        # Expect error message like 'Ошибка авторизации login.vk.com: unauthorized'
        assert "unauthorized" in str(e).lower() or "login.vk.com" in str(e)


if __name__ == "__main__":
    test_token_extraction()
    test_smart_string_parser()
    test_cookie_string_parsing()
    test_oauth_url_generation()
    asyncio.run(test_ssl_http_connection())
    asyncio.run(test_get_web_access_token_endpoint())
    print("All authentication unit tests passed successfully!")
