"""Secure token and credentials storage."""
import json
import os
import base64
import hashlib
from typing import Optional, Dict, Any
from pathlib import Path
from cryptography.fernet import Fernet
from src.core.config import config
from src.core.logger import logger


class SecurityManager:
    """Manages encrypted session tokens and user credentials."""
    
    def __init__(self, key_file: Optional[Path] = None, session_file: Optional[Path] = None):
        self.key_file = key_file or (config.DATA_DIR / ".secret.key")
        self.session_file = session_file or config.SESSION_FILE
        self._cipher = self._init_cipher()

    def _init_cipher(self) -> Fernet:
        """Initializes or loads encryption key."""
        if self.key_file.exists():
            with open(self.key_file, "rb") as f:
                key = f.read()
        else:
            # Generate deterministic salt/key or random key
            key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(key)
        return Fernet(key)

    def save_session(self, token: str, user_id: int, extra_data: Optional[Dict[str, Any]] = None) -> bool:
        """Encrypts and saves user session."""
        try:
            payload = {
                "access_token": token,
                "user_id": user_id,
                "extra": extra_data or {}
            }
            raw_data = json.dumps(payload).encode("utf-8")
            encrypted = self._cipher.encrypt(raw_data)
            with open(self.session_file, "wb") as f:
                f.write(encrypted)
            logger.info("Session saved securely for user_id=%s", user_id)
            return True
        except Exception as e:
            logger.error("Failed to save session: %s", e)
            return False

    def load_session(self) -> Optional[Dict[str, Any]]:
        """Loads and decrypts saved user session."""
        if not self.session_file.exists():
            return None
        try:
            with open(self.session_file, "rb") as f:
                encrypted = f.read()
            decrypted = self._cipher.decrypt(encrypted)
            data = json.loads(decrypted.decode("utf-8"))
            return data
        except Exception as e:
            logger.warning("Failed to decrypt session: %s", e)
            return None

    def clear_session(self) -> bool:
        """Removes the saved session file (logout)."""
        if self.session_file.exists():
            try:
                self.session_file.unlink()
                logger.info("Session file removed.")
                return True
            except Exception as e:
                logger.error("Error removing session: %s", e)
                return False
        return True


security_manager = SecurityManager()
