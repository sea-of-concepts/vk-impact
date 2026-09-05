"""Unit tests for hardware-bound encryption and multi-account management."""
import os
import sys
import tempfile
import asyncio
from pathlib import Path
import pytest
from cryptography.fernet import InvalidToken

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.security import (
    get_hardware_fingerprint,
    derive_hardware_key,
    SecurityManager
)
from src.data.repositories.auth_repo import AuthRepository
from src.data.database.db_manager import DatabaseManager


def test_hardware_fingerprint_deterministic():
    """Verifies that hardware fingerprint is deterministic and non-empty."""
    fp1 = get_hardware_fingerprint()
    fp2 = get_hardware_fingerprint()
    assert fp1, "Fingerprint must not be empty"
    assert fp1 == fp2, "Fingerprint must be deterministic on the same device"

    key1 = derive_hardware_key(fp1)
    key2 = derive_hardware_key(fp2)
    assert key1 == key2, "Derived key must match for identical fingerprints"


def test_hardware_encryption_mismatch():
    """Verifies that data encrypted with one hardware fingerprint cannot be decrypted with another."""
    with tempfile.TemporaryDirectory() as tmpdir:
        acc_file = Path(tmpdir) / "accounts.enc"

        mgr_device1 = SecurityManager(
            accounts_file=acc_file,
            hw_fingerprint="DEVICE_1_HARDWARE_UUID"
        )
        mgr_device2 = SecurityManager(
            accounts_file=acc_file,
            hw_fingerprint="DEVICE_2_DIFFERENT_HARDWARE"
        )

        test_acc = {
            "id": 111,
            "name": "Alice",
            "oauths_metod": "cookie",
            "token": "secret_token_111",
            "remixsid": "sid_111",
            "p": "p_111",
            "is_active": True
        }
        success = mgr_device1.save_or_update_account(test_acc)
        assert success is True

        # Device 1 can load it
        loaded1 = mgr_device1.load_accounts()
        assert len(loaded1) == 1
        assert loaded1[0]["name"] == "Alice"
        assert loaded1[0]["oauths_metod"] == "cookie"

        # Device 2 fails to decrypt (returns empty list / catches error)
        loaded2 = mgr_device2.load_accounts()
        assert len(loaded2) == 0, "Device with different hardware must not be able to decrypt"


def test_multi_account_storage_and_switching():
    """Verifies saving multiple accounts, active flag toggle, and switching."""
    with tempfile.TemporaryDirectory() as tmpdir:
        acc_file = Path(tmpdir) / "accounts.enc"
        mgr = SecurityManager(accounts_file=acc_file, hw_fingerprint="TEST_HW")

        # 1. Add first account
        acc1 = {
            "id": 100,
            "name": "User 100",
            "oauths_metod": "token",
            "token": "tok100",
            "remixsid": "",
            "p": "",
            "is_active": True
        }
        mgr.save_or_update_account(acc1)

        active = mgr.get_active_account()
        assert active is not None
        assert active["id"] == 100
        assert active["is_active"] is True

        # 2. Add second account (also marked active -> should deactivate acc1)
        acc2 = {
            "id": 200,
            "name": "User 200",
            "oauths_metod": "cookie",
            "token": "tok200",
            "remixsid": "sid200",
            "p": "p200",
            "is_active": True
        }
        mgr.save_or_update_account(acc2)

        accounts = mgr.load_accounts()
        assert len(accounts) == 2
        active = mgr.get_active_account()
        assert active["id"] == 200

        for a in accounts:
            if a["id"] == 100:
                assert a["is_active"] is False
            elif a["id"] == 200:
                assert a["is_active"] is True

        # 3. Switch back to account 100
        mgr.set_active_account(100)
        assert mgr.get_active_account()["id"] == 100


def test_delete_account_routing_rules():
    """
    Verifies user's exact specification for account removal:
    - If 1 account: delete returns 'auth'
    - If 2 accounts: delete returns 'switched' (and switches to remaining account)
    - If > 2 accounts: delete returns 'select' (routes to account selection menu)
    """
    async def _test():
        with tempfile.TemporaryDirectory() as tmpdir:
            acc_file = Path(tmpdir) / "accounts.enc"
            mgr = SecurityManager(accounts_file=acc_file, hw_fingerprint="TEST_HW")

            repo = AuthRepository(sec_mgr=mgr)

            # --- Case A: 1 account ---
            mgr.save_or_update_account({
                "id": 1,
                "name": "Only Account",
                "oauths_metod": "token",
                "token": "tok1",
                "is_active": True
            })
            action, remaining = await repo.delete_account(1)
            assert action == "auth"
            assert len(remaining) == 0

            # --- Case B: 2 accounts ---
            mgr.save_or_update_account({
                "id": 1,
                "name": "Account 1",
                "oauths_metod": "token",
                "token": "tok1",
                "is_active": True
            })
            mgr.save_or_update_account({
                "id": 2,
                "name": "Account 2",
                "oauths_metod": "cookie",
                "token": "tok2",
                "remixsid": "sid2",
                "p": "p2",
                "is_active": False
            })
            action, remaining = await repo.delete_account(1)
            assert action == "switched"
            assert len(remaining) == 1
            assert remaining[0]["id"] == 2
            assert mgr.get_active_account()["id"] == 2

            # --- Case C: > 2 accounts (e.g. 3 accounts) ---
            mgr.save_or_update_account({
                "id": 10,
                "name": "Acc 10",
                "oauths_metod": "token",
                "token": "tok10",
                "is_active": True
            })
            mgr.save_or_update_account({
                "id": 20,
                "name": "Acc 20",
                "oauths_metod": "token",
                "token": "tok20",
                "is_active": False
            })
            mgr.save_or_update_account({
                "id": 30,
                "name": "Acc 30",
                "oauths_metod": "token",
                "token": "tok30",
                "is_active": False
            })
            assert len(mgr.load_accounts()) == 4  # (including account 2 from previous step)
            action, remaining = await repo.delete_account(10)
            assert action == "select"
            assert len(remaining) == 3


    asyncio.run(_test())

