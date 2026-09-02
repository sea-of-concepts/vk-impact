import os
import ssl
from pathlib import Path
from dataclasses import dataclass, field

# Patch default SSL context for urllib/kivy loaders on Windows
if hasattr(ssl, "_create_unverified_context"):
    ssl._create_default_https_context = ssl._create_unverified_context



@dataclass
class AppConfig:
    """Global configuration settings for VK_IMPACT."""
    APP_NAME: str = "VK_IMPACT"
    VERSION: str = "0.1.0"
    
    # VK API Settings
    VK_API_VERSION: str = "5.199"
    VK_API_BASE_URL: str = "https://api.vk.com/method/"
    VK_OAUTH_URL: str = "https://oauth.vk.com/token"
    VK_AUTHORIZE_URL: str = "https://oauth.vk.com/authorize"
    
    # SSL & Network Settings
    VERIFY_SSL: bool = False
    DEFAULT_USER_AGENT: str = "KateMobileAndroid/110.1 lite-535 (Android 14; SDK 34; arm64-v8a; Xiaomi 2201116SG; ru)"
    WEB_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    
    # Standard official client IDs (used for direct auth and message access)
    # 2685278 - Kate Mobile (supports direct auth, messages, offline, wall, audio)
    # 2274003 - VK Android
    # 6121396 - VK Me
    CLIENT_ID_KATE: str = "2685278"
    CLIENT_SECRET_KATE: str = "lxhD8OD7dMsqtXIm5LDK"
    
    CLIENT_ID_VK_ANDROID: str = "2274003"
    CLIENT_SECRET_VK_ANDROID: str = "hHbZxrka2uZ6jB1inYsH"
    
    CLIENT_ID_VK_WEB: str = "6287487"
    VK_WEB_APP_ID: str = "6287487"
    
    DEFAULT_CLIENT_ID: str = CLIENT_ID_KATE
    DEFAULT_CLIENT_SECRET: str = CLIENT_SECRET_KATE
    
    # Default scopes (offline, messages, friends, photos, wall, video, audio, groups, docs, notes)
    DEFAULT_SCOPE: int = 1073741823  # All possible permissions
    
    # App storage directory
    BASE_DIR: Path = field(default_factory=lambda: Path(os.path.expanduser("~/.vk_impact")))
    
    @property
    def DATA_DIR(self) -> Path:
        path = self.BASE_DIR / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def CACHE_DIR(self) -> Path:
        path = self.BASE_DIR / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def DB_PATH(self) -> Path:
        return self.DATA_DIR / "vk_impact.db"

    @property
    def SESSION_FILE(self) -> Path:
        return self.DATA_DIR / "session.enc"


config = AppConfig()
