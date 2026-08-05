"""连接器口令加密 (Fernet): 密文落库, 明文只存在于内存."""
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_fernet: Fernet | None = None


def _fernet_instance() -> Fernet:
    global _fernet
    if _fernet is None:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"budai-mesh-salt", iterations=100_000)
        key = kdf.derive(settings.secret_key.encode())
        _fernet = Fernet(key)
    return _fernet


def encrypt_secret(plain: str | None) -> str | None:
    if not plain:
        return None
    return _fernet_instance().encrypt(plain.encode()).decode()


def decrypt_secret(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet_instance().decrypt(token.encode()).decode()
    except InvalidToken:
        logger.warning("口令解密失败, 可能 secret_key 已变更")
        return None
