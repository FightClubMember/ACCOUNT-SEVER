import logging
from cryptography.fernet import Fernet
from bot import config

logger = logging.getLogger(__name__)

# Initialize Fernet cipher
try:
    cipher = Fernet(config.ENCRYPTION_KEY.encode())
except Exception as e:
    logger.critical(f"Failed to initialize Fernet cipher. Invalid key: {e}")
    raise e

def encrypt_password(password: str) -> str:
    """Encrypt a plaintext password string to an encrypted string."""
    if not password:
        return ""
    try:
        encrypted_bytes = cipher.encrypt(password.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to encrypt password: {e}")
        raise RuntimeError("Encryption failed") from e

def decrypt_password(encrypted_password: str) -> str:
    """Decrypt an encrypted password string to a plaintext password string."""
    if not encrypted_password:
        return ""
    try:
        decrypted_bytes = cipher.decrypt(encrypted_password.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to decrypt password: {e}")
        raise RuntimeError("Decryption failed") from e
