"""Application integrity verification and self-healing subsystem.

Monitors core modules against the cryptographic golden manifest (manifest.vault).
If any file is modified or deleted on an unauthorized cloned machine,
it immediately restores the authentic pristine module.
"""

import base64
import hashlib
import hmac
import importlib
import json
from pathlib import Path
import sys
import zlib


_S_KEY = bytes.fromhex("7a4c9b2e81d053f7a62e4c19b83d70ef")


def _get_root_dir() -> Path:
    return Path(__file__).resolve().parent


def _get_vault_path() -> Path:
    return _get_root_dir() / "manifest.vault"


def load_manifest() -> dict:
    vault_path = _get_vault_path()
    if not vault_path.exists():
        raise RuntimeError("Critical integrity violation: manifest.vault is missing.")

    data = vault_path.read_bytes()
    if len(data) < 32:
        raise RuntimeError("Critical integrity violation: manifest.vault is corrupted.")

    signature = data[:32]
    compressed_payload = data[32:]
    expected_sig = hmac.new(_S_KEY, compressed_payload, hashlib.sha256).digest()

    if not hmac.compare_digest(signature, expected_sig):
        raise RuntimeError("Critical integrity violation: manifest signature verification failed.")

    try:
        raw_json = zlib.decompress(compressed_payload).decode("utf-8")
        return json.loads(raw_json)
    except Exception as err:
        raise RuntimeError(f"Critical integrity violation: cannot read manifest payload: {err}")


def verify_and_repair_manifest(force: bool = False) -> bool:
    """Verifies core files against the golden manifest and restores any tampered files.

    If run inside an unauthorized cloned copy or if force=True:
    Any tampered, modified, or missing file is immediately restored from manifest.vault.
    If run on an authorized developer device, missing files are restored, but local
    edits are preserved for development.
    """
    root_dir = _get_root_dir()

    is_dev = False
    try:
        import security
        is_dev = security.is_device_authorized()
    except Exception:
        is_dev = False

    manifest = load_manifest()
    files = manifest.get("files", {})

    for filename, meta in files.items():
        filepath = root_dir / filename
        golden_sha = meta.get("sha256", "")
        compressed_data = base64.b64decode(meta.get("data_b64", "").encode("ascii"))
        pristine_bytes = zlib.decompress(compressed_data)

        needs_repair = False
        if not filepath.exists():
            needs_repair = True
        elif force or not is_dev:
            try:
                current_bytes = filepath.read_bytes().replace(b"\r\n", b"\n")
                current_sha = hashlib.sha256(current_bytes).hexdigest()
                if not hmac.compare_digest(current_sha, golden_sha):
                    needs_repair = True
            except Exception:
                needs_repair = True

        if needs_repair:
            try:
                filepath.write_bytes(pristine_bytes)
                mod_name = Path(filename).stem
                if mod_name in sys.modules:
                    mod = sys.modules[mod_name]
                    importlib.reload(mod)
            except Exception as err:
                raise RuntimeError(f"Integrity self-healing failure on {filename}: {err}")

    return True


# Run integrity verification automatically on import
verify_and_repair_manifest()


if __name__ == "__main__":
    force_repair = "--repair" in sys.argv or "-r" in sys.argv
    print("=" * 55)
    print("  Business Budget AI — Integrity Audit & Self-Healing")
    print("=" * 55)
    try:
        manifest = load_manifest()
        print("Vault Status: VALID (HMAC-SHA256 signature verified)")
        print(f"Vault Contains: {len(manifest.get('files', {}))} core modules\n")
    except Exception as exc:
        print(f"Vault Status: ERROR ({exc})")
        print("\nTo rebuild the manifest vault from current working files, run:")
        print("    python update_manifest.py\n")
        sys.exit(1)

    root_dir = _get_root_dir()
    files = manifest.get("files", {})
    repaired_count = 0
    ok_count = 0

    for filename, meta in files.items():
        filepath = root_dir / filename
        golden_sha = meta.get("sha256", "")
        status = "OK"

        if not filepath.exists():
            status = "MISSING"
        else:
            try:
                curr = filepath.read_bytes().replace(b"\r\n", b"\n")
                if not hmac.compare_digest(hashlib.sha256(curr).hexdigest(), golden_sha):
                    status = "MODIFIED"
            except Exception:
                status = "CORRUPT"

        if status != "OK":
            if force_repair:
                try:
                    compressed = base64.b64decode(meta.get("data_b64", "").encode("ascii"))
                    filepath.write_bytes(zlib.decompress(compressed))
                    print(f"  [REPAIRED] {filename:<22} (Restored from manifest.vault)")
                    repaired_count += 1
                except Exception as err:
                    print(f"  [FAILED]   {filename:<22} (Repair error: {err})")
            else:
                print(f"  [ALERT]    {filename:<22} ({status})")
        else:
            print(f"  [OK]       {filename:<22} (Pristine)")
            ok_count += 1

    print("\n" + "-" * 55)
    if repaired_count > 0:
        print(f"Integrity Repair Complete: {repaired_count} file(s) restored.")
    elif ok_count == len(files):
        print("Integrity Status: 100% HEALTHY — All core files are pristine.")
    else:
        print("Integrity Alert: File mismatches detected.")
        print("To automatically repair all files, run:")
        print("    python integrity.py --repair")
    print("-" * 55)
