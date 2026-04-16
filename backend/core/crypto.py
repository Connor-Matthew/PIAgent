from cryptography.fernet import Fernet

from backend.config import settings


def get_fernet() -> Fernet:
    key = settings.secret_key.get_secret_value()
    if not key:
        raise RuntimeError("SECRET_KEY is not configured")
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    f = get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    f = get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


def mask_key(plaintext: str) -> str:
    if len(plaintext) <= 4:
        return "***"
    return "sk-***" + plaintext[-4:]
