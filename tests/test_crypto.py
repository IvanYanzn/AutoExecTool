from __future__ import annotations

from pathlib import Path

from autoexectool.security.crypto import CredentialVault, MasterKeyManager


def test_master_and_vault(tmp_path: Path) -> None:
    master = MasterKeyManager(tmp_path / "keys")
    master.initialize("test-pass-123")
    assert master.is_unlocked
    vault = CredentialVault(master)
    blob = vault.encrypt_payload({"username": "u1", "password": "p1"})
    master.lock()
    master.unlock("test-pass-123")
    data = vault.decrypt_payload(blob)
    assert data["username"] == "u1"
    assert data["password"] == "p1"
