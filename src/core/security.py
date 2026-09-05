"""Secure token, credentials, and multi-account storage with hardware-based encryption."""
import json
import os
import uuid
import base64
import platform
from typing import Optional, Dict, Any, List
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from src.core.config import config
from src.core.logger import logger


def get_hardware_fingerprint() -> str:
    """
    Extracts deterministic hardware identifiers for key derivation.
    On Windows: MachineGuid + PROCESSOR_IDENTIFIER + MAC node.
    On Linux/others: /etc/machine-id + Processor + MAC node.
    """
    parts: List[str] = []

    # 1. Windows MachineGuid from registry
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
            guid, _ = winreg.QueryValueEx(k, "MachineGuid")
            if guid:
                parts.append(str(guid).strip())
    except Exception:
        pass

    # 2. Linux / macOS machine-id fallback
    try:
        mid_path = Path("/etc/machine-id")
        if mid_path.exists():
            parts.append(mid_path.read_text().strip())
    except Exception:
        pass

    # 3. Processor Identifier / Architecture
    proc_id = os.environ.get("PROCESSOR_IDENTIFIER") or platform.processor() or platform.machine()
    parts.append(str(proc_id).strip())

    # 4. Hardware MAC address node
    parts.append(str(uuid.getnode()))

    # Fallback if somehow empty
    if not parts:
        parts.append(platform.node())

    return ":".join(parts)


def derive_hardware_key(fingerprint: Optional[str] = None, salt: bytes = b"VK_IMPACT_HW_SALT_v1") -> bytes:
    """
    Derives a 256-bit Fernet key from the hardware fingerprint using PBKDF2HMAC-SHA256.
    """
    hw_str = (fingerprint or get_hardware_fingerprint()).encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000
    )
    return base64.urlsafe_b64encode(kdf.derive(hw_str))


class SecurityManager:
    """Manages hardware-encrypted accounts and session storage."""

    def __init__(
        self,
        accounts_file: Optional[Path] = None,
        key_file: Optional[Path] = None,
        session_file: Optional[Path] = None,
        hw_fingerprint: Optional[str] = None
    ):
        if accounts_file is not None:
            self.accounts_file = accounts_file
        elif session_file is not None:
            self.accounts_file = session_file.parent / "accounts.enc"
        else:
            self.accounts_file = config.ACCOUNTS_FILE

        self.key_file = key_file or (self.accounts_file.parent / ".secret.key")
        self.session_file = session_file or (self.accounts_file.parent / "session.enc")
        self._hw_fingerprint = hw_fingerprint
        self._cipher = self._init_hardware_cipher()


    def _init_hardware_cipher(self) -> Fernet:
        """Derives hardware encryption key directly from device parameters."""
        key = derive_hardware_key(self._hw_fingerprint)
        return Fernet(key)

    # -------------------------------------------------------------------------
    # Multi-account operations
    # -------------------------------------------------------------------------

    def load_accounts(self) -> List[Dict[str, Any]]:
        """Loads and decrypts the list of accounts from accounts.enc."""
        if not self.accounts_file.exists():
            # Check for legacy session migration
            migrated = self._migrate_legacy_session()
            if migrated:
                return [migrated]
            return []

        try:
            with open(self.accounts_file, "rb") as f:
                encrypted = f.read()
            if not encrypted:
                return []
            decrypted = self._cipher.decrypt(encrypted)
            data = json.loads(decrypted.decode("utf-8"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "accounts" in data:
                return data["accounts"]
            return []
        except Exception as e:
            logger.warning("Failed to decrypt accounts file: %s", e)
            return []

    def save_accounts(self, accounts: List[Dict[str, Any]]) -> bool:
        """Encrypts and writes the accounts list to accounts.enc."""
        try:
            self.accounts_file.parent.mkdir(parents=True, exist_ok=True)
            raw_data = json.dumps(accounts, ensure_ascii=False).encode("utf-8")
            encrypted = self._cipher.encrypt(raw_data)
            with open(self.accounts_file, "wb") as f:
                f.write(encrypted)
            logger.info("Saved %d account(s) securely.", len(accounts))
            return True
        except Exception as e:
            logger.error("Failed to save accounts: %s", e)
            return False

    def get_active_account(self) -> Optional[Dict[str, Any]]:
        """Returns the currently active account, or the first account if none marked."""
        accounts = self.load_accounts()
        if not accounts:
            return None
        for acc in accounts:
            if acc.get("is_active"):
                return acc
        # Fallback to first account
        accounts[0]["is_active"] = True
        self.save_accounts(accounts)
        return accounts[0]

    def save_or_update_account(self, account_data: Dict[str, Any]) -> bool:
        """
        Adds or updates an account.
        If account_data['is_active'] is True, other accounts will be set to is_active=False.
        """
        accounts = self.load_accounts()
        user_id = account_data.get("id") or account_data.get("uid") or account_data.get("user_id")
        if not user_id:
            logger.error("Cannot save account without valid ID")
            return False

        user_id = int(user_id)
        is_active = bool(account_data.get("is_active", True))

        if is_active:
            for acc in accounts:
                acc["is_active"] = False

        # Format record
        record = {
            "id": user_id,
            "uid": user_id,
            "name": account_data.get("name") or account_data.get("full_name") or f"id{user_id}",
            "avatar_url": account_data.get("avatar_url") or account_data.get("photo_100") or "",
            "impact_style": account_data.get("impact_style") or "",
            "oauths_metod": account_data.get("oauths_metod") or account_data.get("oauth_method") or "token",
            "token": account_data.get("token") or account_data.get("access_token") or "",
            "remixsid": account_data.get("remixsid") or "",
            "p": account_data.get("p") or "",
            "extra": account_data.get("extra") or {},
            "is_active": is_active
        }

        # Update if exists, else append
        found = False
        for i, acc in enumerate(accounts):
            if int(acc.get("id", 0)) == user_id:
                # Merge existing fields if not provided
                if not record["name"] and acc.get("name"):
                    record["name"] = acc["name"]
                if not record["avatar_url"] and acc.get("avatar_url"):
                    record["avatar_url"] = acc["avatar_url"]
                if not record["impact_style"] and acc.get("impact_style"):
                    record["impact_style"] = acc["impact_style"]
                if not record["remixsid"] and acc.get("remixsid"):
                    record["remixsid"] = acc["remixsid"]
                if not record["p"] and acc.get("p"):
                    record["p"] = acc["p"]
                accounts[i] = record
                found = True
                break

        if not found:
            accounts.append(record)

        return self.save_accounts(accounts)

    def set_active_account(self, user_id: int) -> bool:
        """Sets the specified user_id as the active account."""
        accounts = self.load_accounts()
        found = False
        for acc in accounts:
            if int(acc.get("id", 0)) == int(user_id):
                acc["is_active"] = True
                found = True
            else:
                acc["is_active"] = False

        if found:
            return self.save_accounts(accounts)
        return False

    def remove_account(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Removes account with user_id.
        If removed account was active, activates the first remaining account.
        Returns the updated list of remaining accounts.
        """
        accounts = self.load_accounts()
        was_active = False
        new_accounts = []
        for acc in accounts:
            if int(acc.get("id", 0)) == int(user_id):
                if acc.get("is_active"):
                    was_active = True
            else:
                new_accounts.append(acc)

        if was_active and new_accounts:
            new_accounts[0]["is_active"] = True

        if new_accounts:
            self.save_accounts(new_accounts)
        else:
            if self.accounts_file.exists():
                try:
                    self.accounts_file.unlink()
                except Exception as e:
                    logger.warning("Could not delete accounts file: %s", e)

        return new_accounts

    def clear_all_accounts(self) -> bool:
        """Clears all stored accounts and sessions."""
        success = True
        if self.accounts_file.exists():
            try:
                self.accounts_file.unlink()
            except Exception as e:
                logger.error("Failed to delete accounts file: %s", e)
                success = False
        if self.session_file.exists():
            try:
                self.session_file.unlink()
            except Exception as e:
                logger.error("Failed to delete session file: %s", e)
                success = False
        return success

    # -------------------------------------------------------------------------
    # Legacy migration & compatibility
    # -------------------------------------------------------------------------

    def _migrate_legacy_session(self) -> Optional[Dict[str, Any]]:
        """Attempts to read old session.enc (using legacy .secret.key) and migrates it."""
        if not self.session_file.exists() or not self.key_file.exists():
            return None

        try:
            with open(self.key_file, "rb") as f:
                key = f.read()
            legacy_cipher = Fernet(key)
            with open(self.session_file, "rb") as f:
                encrypted = f.read()
            decrypted = legacy_cipher.decrypt(encrypted)
            data = json.loads(decrypted.decode("utf-8"))

            token = data.get("access_token", "")
            user_id = int(data.get("user_id", 0))
            extra = data.get("extra", {})
            cookies = extra.get("cookies", {})

            remixsid = cookies.get("remixsid", "")
            p_cookie = cookies.get("p", "")
            oauths_metod = "cookie" if remixsid else "token"

            account = {
                "id": user_id,
                "uid": user_id,
                "name": f"id{user_id}",
                "avatar_url": "",
                "impact_style": "",
                "oauths_metod": oauths_metod,
                "token": token,
                "remixsid": remixsid,
                "p": p_cookie,
                "is_active": True
            }

            self.save_accounts([account])
            logger.info("Successfully migrated legacy session for user_id=%s to accounts.enc", user_id)
            return account
        except Exception as e:
            logger.warning("Could not migrate legacy session: %s", e)
            return None

    # Backward compatibility with existing calls
    def save_session(self, token: str, user_id: int, extra_data: Optional[Dict[str, Any]] = None) -> bool:
        extra = extra_data or {}
        cookies = extra.get("cookies", {})
        remixsid = cookies.get("remixsid", "")
        p_val = cookies.get("p", "")
        return self.save_or_update_account({
            "id": user_id,
            "token": token,
            "remixsid": remixsid,
            "p": p_val,
            "extra": extra,
            "oauths_metod": "cookie" if remixsid else "token",
            "is_active": True
        })

    def load_session(self) -> Optional[Dict[str, Any]]:
        acc = self.get_active_account()
        if not acc:
            return None
        extra = dict(acc.get("extra") or {})
        if "cookies" not in extra:
            extra["cookies"] = {
                "remixsid": acc.get("remixsid", ""),
                "p": acc.get("p", "")
            }
        return {
            "access_token": acc.get("token", ""),
            "user_id": acc.get("id", 0),
            "extra": extra
        }

    def clear_session(self) -> bool:
        acc = self.get_active_account()
        if acc:
            self.remove_account(acc.get("id", 0))
        return True


security_manager = SecurityManager()
