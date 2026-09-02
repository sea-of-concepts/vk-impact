"""Centralized HTTP session and connector factory."""
import ssl
from typing import Optional, Dict, Any
import aiohttp
from src.core.config import config


def create_ssl_connector() -> aiohttp.TCPConnector:
    """
    Creates an aiohttp TCPConnector with SSL verification disabled or custom configured,
    preventing Windows root CA validation errors when connecting to VK servers.
    """
    if not config.VERIFY_SSL:
        return aiohttp.TCPConnector(ssl=False)
    return aiohttp.TCPConnector()


def create_http_session(
    headers: Optional[Dict[str, str]] = None,
    cookie_jar: Optional[aiohttp.CookieJar] = None,
    timeout_seconds: float = 20.0
) -> aiohttp.ClientSession:
    """Creates a configured aiohttp.ClientSession with proper headers, cookies and SSL settings."""
    default_headers = {
        "User-Agent": config.DEFAULT_USER_AGENT,
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "*/*"
    }
    if headers:
        default_headers.update(headers)

    connector = create_ssl_connector()
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    return aiohttp.ClientSession(
        connector=connector,
        headers=default_headers,
        cookie_jar=cookie_jar or aiohttp.CookieJar(unsafe=True),
        timeout=timeout
    )
