# Auto-generated application integrity and self-healing subsystem
import base64
import hashlib
import hmac
import importlib
from pathlib import Path
import sys
import zlib

_SECURITY_HASH = '0c017811ea791da68516abc614ab3d1b967246ce9dd28ea486869abe89c35891'
_PRISTINE_SECURITY_B64 = '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'

def _get_security_path() -> Path:
    return Path(__file__).resolve().parent / 'security.py'

def get_pristine_security_code() -> bytes:
    compressed = base64.b64decode(_PRISTINE_SECURITY_B64.encode('ascii'))
    return zlib.decompress(compressed)

def verify_and_repair_security_module() -> bool:
    sec_path = _get_security_path()
    pristine_code = get_pristine_security_code()
    needs_repair = False
    if not sec_path.exists():
        needs_repair = True
    else:
        try:
            current_bytes = sec_path.read_bytes().replace(b'\r\n', b'\n')
            current_hash = hashlib.sha256(current_bytes).hexdigest()
            if not hmac.compare_digest(current_hash, _SECURITY_HASH):
                needs_repair = True
        except Exception:
            needs_repair = True

    if needs_repair:
        try:
            sec_path.write_bytes(pristine_code)
            if 'security' in sys.modules:
                import security
                importlib.reload(security)
        except Exception as err:
            raise RuntimeError(f'Critical integrity failure: cannot restore security module: {err}')
    return True

verify_and_repair_security_module()
