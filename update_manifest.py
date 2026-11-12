"""Golden Manifest Generator and Updater.

Run this script after making authorized updates to core application modules
to recalculate cryptographic hashes, update the compressed golden backup archive,
and HMAC-sign the manifest.vault package.
"""

import base64
import hashlib
import hmac
import json
from pathlib import Path
import sys
import zlib


_S_KEY = bytes.fromhex("7a4c9b2e81d053f7a62e4c19b83d70ef")

CORE_FILES = [
    "security.py",
    "integrity.py",
    "app.py",
    "desktop_app.py",
    "budget.py",
    "ai.py",
    "bookkeeping.py",
    "quickbooks.py",
    "shopping_api.py",
    "secure_storage.py",
    "config.py",
]


def update_manifest(root_dir=None):
    if root_dir is None:
        root_dir = Path(__file__).resolve().parent
    else:
        root_dir = Path(root_dir).resolve()

    manifest = {"files": {}}
    for filename in CORE_FILES:
        filepath = root_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Required core file not found: {filename}")
        data = filepath.read_bytes().replace(b"\r\n", b"\n")
        manifest["files"][filename] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "data_b64": base64.b64encode(zlib.compress(data, 9)).decode("ascii"),
        }

    raw_json = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(raw_json, 9)
    signature = hmac.new(_S_KEY, compressed, hashlib.sha256).digest()
    vault_data = signature + compressed

    vault_path = root_dir / "manifest.vault"
    vault_path.write_bytes(vault_data)
    print(f"[Golden Manifest] Updated {vault_path.name} with {len(CORE_FILES)} core modules ({len(vault_data):,} bytes).")
    return True


if __name__ == "__main__":
    update_manifest()
