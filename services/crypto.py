import os
from cryptography.fernet import Fernet

_key = os.getenv("FERNET_KEY", "")
if not _key:
    raise RuntimeError("FERNET_KEY не задан в .env")

_fernet = Fernet(_key.encode() if isinstance(_key, str) else _key)


def encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _fernet.decrypt(value.encode()).decode()