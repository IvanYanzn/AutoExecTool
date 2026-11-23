from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from autoexectool.domain.errors import AppError, ErrorCode

_KDF_ITERATIONS = 200_000
_SALT_LEN = 16
_NONCE_LEN = 12


class MasterKeyManager:
    """主密码派生与校验（盐值与校验密文落在 data/config/keys）。"""

    def __init__(self, keys_dir: Path) -> None:
        self.keys_dir = keys_dir
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self._meta_path = self.keys_dir / "master.meta"
        self._key: bytes | None = None

    @property
    def is_initialized(self) -> bool:
        return self._meta_path.exists()

    @property
    def is_unlocked(self) -> bool:
        return self._key is not None

    def initialize(self, master_password: str) -> None:
        if self.is_initialized:
            raise AppError(ErrorCode.VALIDATION_ERROR, "主密码已初始化，不可重复创建。")
        salt = os.urandom(_SALT_LEN)
        key = self._derive(master_password, salt)
        nonce = os.urandom(_NONCE_LEN)
        ciphertext = AESGCM(key).encrypt(nonce, b"autoexectool-ok", None)
        verifier = nonce + ciphertext
        payload = {
            "salt": base64.b64encode(salt).decode("ascii"),
            "verifier": base64.b64encode(verifier).decode("ascii"),
            "kdf": "pbkdf2-sha256",
            "iterations": _KDF_ITERATIONS,
        }
        self._meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._key = key

    def unlock(self, master_password: str) -> None:
        if not self.is_initialized:
            raise AppError(ErrorCode.NOT_INITIALIZED, "尚未设置主密码。")
        meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
        salt = base64.b64decode(meta["salt"])
        key = self._derive(master_password, salt)
        try:
            raw = base64.b64decode(meta["verifier"])
            nonce, ciphertext = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
            AESGCM(key).decrypt(nonce, ciphertext, None)
        except Exception as exc:  # noqa: BLE001
            raise AppError(ErrorCode.CRYPTO_ERROR, "主密码不正确。") from exc
        self._key = key

    def lock(self) -> None:
        self._key = None

    def require_key(self) -> bytes:
        if self._key is None:
            raise AppError(ErrorCode.NOT_INITIALIZED, "保险库未解锁，请先输入主密码。")
        return self._key

    @staticmethod
    def _derive(password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=_KDF_ITERATIONS,
        )
        return kdf.derive(password.encode("utf-8"))


class CredentialVault:
    """凭证字段加解密（AES-GCM）。"""

    def __init__(self, master: MasterKeyManager) -> None:
        self._master = master

    def encrypt_payload(self, data: dict) -> str:
        key = self._master.require_key()
        nonce = os.urandom(_NONCE_LEN)
        plaintext = json.dumps(data, ensure_ascii=False).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
        blob = base64.b64encode(nonce + ciphertext).decode("ascii")
        return blob

    def decrypt_payload(self, blob: str) -> dict:
        key = self._master.require_key()
        raw = base64.b64decode(blob)
        nonce, ciphertext = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
        except Exception as exc:  # noqa: BLE001
            raise AppError(ErrorCode.CRYPTO_ERROR) from exc
        return json.loads(plaintext.decode("utf-8"))
