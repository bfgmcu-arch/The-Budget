import os
from pathlib import Path

import keyring
from cryptography.fernet import Fernet, InvalidToken

import security
security.ensure_integrity_module()
import integrity
from security import enforce_runtime_authorization

enforce_runtime_authorization()


_MAGIC = b"BUDGETAI-ENCRYPTED-V1\0"
_SERVICE_NAME = "BusinessBudgetAI"
_KEY_NAME = "local-file-encryption-key"
_SECURE_BACKENDS = (
    "keyring.backends.Windows",
    "keyring.backends.macOS",
    "keyring.backends.SecretService",
)
_CACHED_CIPHER = None


class SecureStorageError(RuntimeError):
    pass


def _get_cipher():
    global _CACHED_CIPHER
    if _CACHED_CIPHER is not None:
        return _CACHED_CIPHER

    from security import is_runtime_authorized
    if not is_runtime_authorized():
        raise SecureStorageError("Unauthorized execution environment. Security verification failed.")

    backend = keyring.get_keyring()
    backend_module = type(backend).__module__
    if not any(backend_module.startswith(name) for name in _SECURE_BACKENDS):
        raise SecureStorageError(
            "No supported operating-system credential store is available. "
            "Use Windows Credential Manager, macOS Keychain, or Linux Secret Service."
        )

    try:
        key = keyring.get_password(_SERVICE_NAME, _KEY_NAME)
        if key is None:
            key = Fernet.generate_key().decode("ascii")
            keyring.set_password(_SERVICE_NAME, _KEY_NAME, key)
            stored_key = keyring.get_password(_SERVICE_NAME, _KEY_NAME)
            if stored_key != key:
                raise SecureStorageError("The operating-system credential store did not save the encryption key.")
        _CACHED_CIPHER = Fernet(key.encode("ascii"))
        return _CACHED_CIPHER
    except SecureStorageError:
        raise
    except Exception as exc:
        raise SecureStorageError(f"Could not access the operating-system credential store: {exc}") from exc


def encrypt_bytes(data):
    return _MAGIC + _get_cipher().encrypt(data)


def decrypt_bytes(data):
    if not data.startswith(_MAGIC):
        return data, False
    try:
        return _get_cipher().decrypt(data[len(_MAGIC):]), True
    except InvalidToken as exc:
        raise SecureStorageError(
            "This encrypted file cannot be unlocked with this operating-system account."
        ) from exc


def read_file(path):
    try:
        return decrypt_bytes(Path(path).read_bytes())
    except OSError as exc:
        raise SecureStorageError(f"Could not read protected data: {exc}") from exc


def write_file(path, data):
    path = Path(path)
    temporary_path = path.with_name(path.name + ".tmp")
    protected_data = encrypt_bytes(data)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(protected_data)
        os.replace(temporary_path, path)
    except OSError as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise SecureStorageError(f"Could not save protected data: {exc}") from exc
