"""SSH 密钥生成与公钥落盘（私钥不进明文文件）。"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import paramiko
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from autoexectool.domain.errors import AppError, ErrorCode


def generate_ed25519_keypair(*, comment: str = "autoexectool") -> tuple[str, str]:
    """返回 (private_key_openssh, public_key_line)。"""
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_openssh = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")
    public_line = f"{public_openssh} {comment}".strip()
    return private_pem, public_line


def load_private_key(pem: str, passphrase: str = ""):
    """按常见算法尝试加载私钥（Ed25519 / ECDSA / RSA）。"""
    last_err: Exception | None = None
    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return cls.from_private_key(
                StringIO(pem), password=passphrase or None
            )
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise AppError(
        ErrorCode.AUTH_FAILED,
        "无法解析私钥（支持 Ed25519/ECDSA/RSA）",
        detail=str(last_err) if last_err else "",
    )


def write_public_key_file(path: Path, public_line: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = public_line.strip() + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def user_ssh_dir() -> Path:
    return Path.home() / ".ssh"


def ensure_user_openssh_ed25519(
    *, comment: str = "autoexectool-openssh"
) -> tuple[Path, Path, str, bool]:
    """确保本机用户目录存在 OpenSSH Ed25519 密钥对。

    返回 (private_path, public_path, public_line, created_new)。
    供方案 A（本机 ssh/scp）免密使用；私钥在用户 ~/.ssh，不进程序保险库。
    """
    ssh_dir = user_ssh_dir()
    ssh_dir.mkdir(parents=True, exist_ok=True)
    priv = ssh_dir / "id_ed25519"
    pub = ssh_dir / "id_ed25519.pub"
    if priv.exists() and pub.exists():
        line = pub.read_text(encoding="utf-8").strip()
        return priv, pub, line, False
    if priv.exists() and not pub.exists():
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"发现私钥 {priv} 但缺少公钥文件，请手动补全或删除后重试。",
        )
    private_pem, public_line = generate_ed25519_keypair(comment=comment)
    priv.write_text(private_pem, encoding="utf-8")
    try:
        priv.chmod(0o600)
    except OSError:
        pass
    write_public_key_file(pub, public_line)
    return priv, pub, public_line, True


def remote_install_authorized_key_script(public_line: str) -> str:
    """生成在 Linux 上追加 authorized_keys 的 shell 脚本。"""
    safe = public_line.strip().replace("'", "'\"'\"'")
    return (
        "set -e; mkdir -p ~/.ssh; chmod 700 ~/.ssh; touch ~/.ssh/authorized_keys; "
        "chmod 600 ~/.ssh/authorized_keys; "
        f"grep -qxF '{safe}' ~/.ssh/authorized_keys || "
        f"echo '{safe}' >> ~/.ssh/authorized_keys; echo installed_ok"
    )


def public_key_from_private_pem(pem: str, passphrase: str = "", comment: str = "") -> str:
    key = load_private_key(pem, passphrase)
    suffix = f" {comment}" if comment else ""
    return f"{key.get_name()} {key.get_base64()}{suffix}".strip()
