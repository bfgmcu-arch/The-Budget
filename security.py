import base64
import hashlib
import hmac
import importlib
import json
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser
import zlib

import keyring


# Cryptographic authorization tokens (hex-encoded binary)
_K_SALT = bytes.fromhex("9e1f4a8bcd33127f55a0ef612894b7d2")
_K_VERIFIER = bytes.fromhex("fbe273b741887c4c6ae7f5c87e8b96504a2f45a57de953c413a77c738a3969cb")
_K_ROUNDS = 120000

_S_KEY = bytes.fromhex("7a4c9b2e81d053f7a62e4c19b83d70ef")
_S_DATA = bytes.fromhex("3f9a1c8b2e5d7041a8b9c2e3f4a5b6c7")

_SERVICE_NAME = "BusinessBudgetAI"
_AUTH_KEY_NAME = "clone-dev-authorization"
_IS_RUNTIME_AUTHORIZED = False
_INSTALLER_RELEASES_URL = "https://github.com/bfgmcu-arch/The-Budget/releases"


def open_installer_page():
    """Opens the official installer download page in the default web browser."""
    try:
        webbrowser.open(_INSTALLER_RELEASES_URL)
    except Exception:
        pass

_INTEGRITY_BACKUP_SHA256 = "1b053b8b2ef047106db4aa1a82c4d96d15a3277ac877184a9eeed89999bbc3b4"
_INTEGRITY_BACKUP_B64 = "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"


def _read_manifest_from_security() -> dict:
    root_dir = Path(__file__).resolve().parent
    vault_path = root_dir / "manifest.vault"
    if not vault_path.exists():
        return {}
    try:
        data = vault_path.read_bytes()
        if len(data) < 32:
            return {}
        signature = data[:32]
        payload = data[32:]
        expected_sig = hmac.new(_S_KEY, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected_sig):
            return {}
        raw = zlib.decompress(payload).decode("utf-8")
        return json.loads(raw)
    except Exception:
        return {}


def repair_integrity_module(force: bool = False) -> bool:
    """Restores integrity.py from manifest.vault or the embedded cryptographic fallback."""
    root_dir = Path(__file__).resolve().parent
    integrity_path = root_dir / "integrity.py"

    restored_bytes = None
    manifest = _read_manifest_from_security()
    if manifest and "files" in manifest and "integrity.py" in manifest.get("files", {}):
        try:
            data_b64 = manifest["files"]["integrity.py"].get("data_b64", "")
            if data_b64:
                compressed = base64.b64decode(data_b64.encode("ascii"))
                restored_bytes = zlib.decompress(compressed)
        except Exception:
            restored_bytes = None

    if not restored_bytes and _INTEGRITY_BACKUP_B64:
        try:
            compressed = base64.b64decode(_INTEGRITY_BACKUP_B64.encode("ascii"))
            restored_bytes = zlib.decompress(compressed)
        except Exception:
            restored_bytes = None

    if not restored_bytes:
        return False

    try:
        integrity_path.write_bytes(restored_bytes)
        if "integrity" in sys.modules:
            importlib.reload(sys.modules["integrity"])
        return True
    except Exception:
        return False


def ensure_integrity_module(force: bool = False) -> bool:
    """Verifies that integrity.py exists and is authentic.

    If integrity.py is missing, corrupted, or altered on an unauthorized device,
    this function immediately repairs and resurrects it.
    """
    root_dir = Path(__file__).resolve().parent
    integrity_path = root_dir / "integrity.py"

    if not integrity_path.exists():
        return repair_integrity_module(force=True)

    if force:
        return repair_integrity_module(force=True)

    if is_device_authorized():
        return True

    try:
        current_bytes = integrity_path.read_bytes().replace(b"\r\n", b"\n")
        current_sha = hashlib.sha256(current_bytes).hexdigest()

        manifest = _read_manifest_from_security()
        golden_sha = ""
        if manifest and "files" in manifest and "integrity.py" in manifest.get("files", {}):
            golden_sha = manifest["files"]["integrity.py"].get("sha256", "")

        if not golden_sha:
            golden_sha = _INTEGRITY_BACKUP_SHA256

        if not hmac.compare_digest(current_sha, golden_sha):
            return repair_integrity_module(force=True)
    except Exception:
        return repair_integrity_module(force=True)

    return True



def is_runtime_authorized() -> bool:
    global _IS_RUNTIME_AUTHORIZED
    if _IS_RUNTIME_AUTHORIZED:
        return True
    if not is_cloned_or_source_build():
        _IS_RUNTIME_AUTHORIZED = True
        return True
    if is_device_authorized():
        _IS_RUNTIME_AUTHORIZED = True
        return True
    return False


def get_expected_install_signature() -> str:
    return hmac.new(_S_KEY, _S_DATA, hashlib.sha256).hexdigest()


def is_cloned_or_source_build(app_dir=None) -> bool:
    if app_dir is None:
        app_dir = Path(__file__).resolve().parent
    else:
        app_dir = Path(app_dir).resolve()

    check_dir = app_dir
    for _ in range(3):
        if (check_dir / ".git").exists():
            return True
        check_dir = check_dir.parent

    sig_file = app_dir / ".install_signature"
    if not sig_file.exists():
        return True

    try:
        content = sig_file.read_text(encoding="utf-8").strip()
        expected = get_expected_install_signature()
        if not hmac.compare_digest(content, expected):
            return True
    except Exception:
        return True

    return False


def verify_admin_password(password: str) -> bool:
    if not password:
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _K_SALT, _K_ROUNDS)
    return hmac.compare_digest(derived, _K_VERIFIER)


def is_device_authorized() -> bool:
    try:
        token = keyring.get_password(_SERVICE_NAME, _AUTH_KEY_NAME)
        if token:
            expected = hashlib.sha256(_K_SALT + _K_VERIFIER).hexdigest()
            return hmac.compare_digest(token, expected)
    except Exception:
        pass
    return False


def remember_device_authorization():
    try:
        token = hashlib.sha256(_K_SALT + _K_VERIFIER).hexdigest()
        keyring.set_password(_SERVICE_NAME, _AUTH_KEY_NAME, token)
        return True
    except Exception:
        return False


def revoke_device_authorization() -> bool:
    """Removes stored authorization credentials from the Windows Credential Store."""
    global _IS_RUNTIME_AUTHORIZED
    _IS_RUNTIME_AUTHORIZED = False
    try:
        keyring.delete_password(_SERVICE_NAME, _AUTH_KEY_NAME)
        return True
    except Exception:
        return False


def require_launch_authorization(parent=None) -> bool:
    global _IS_RUNTIME_AUTHORIZED
    if not is_cloned_or_source_build():
        _IS_RUNTIME_AUTHORIZED = True
        return True

    if is_device_authorized():
        _IS_RUNTIME_AUTHORIZED = True
        return True

    try:
        res = _prompt_authorization_dialog(parent)
    except Exception:
        import getpass
        try:
            print("\n" + "=" * 60)
            print("  Business Budget AI — Security Verification")
            print("=" * 60)
            print("If you are not an admin, please download this file via the installer:")
            print(f"    {_INSTALLER_RELEASES_URL}\n")
            print("Cloned repository detected. Running from source requires administrator authorization.")
            entered = getpass.getpass("Administrator Password: ")
            if verify_admin_password(entered):
                remember_device_authorization()
                res = True
            else:
                print("\nAccess denied: Incorrect administrator password.")
                print("If you are not an admin, please download this file via the installer:")
                print(f"    {_INSTALLER_RELEASES_URL}\n")
                res = False
        except Exception:
            res = False

    if res:
        _IS_RUNTIME_AUTHORIZED = True
    return bool(res)


def enforce_runtime_authorization(parent=None) -> bool:
    """Enforces runtime authorization across all application modules.

    Also verifies and repairs integrity.py if missing or altered.
    If running inside an uninstalled or cloned repository, checks for device
    authorization or prompts for administrator verification. Raises PermissionError
    if unverified.
    """
    ensure_integrity_module()
    global _IS_RUNTIME_AUTHORIZED
    if _IS_RUNTIME_AUTHORIZED:
        return True
    if not require_launch_authorization(parent=parent):
        raise PermissionError(
            f"Access Denied: If you are not an admin, please download this file via the installer ({_INSTALLER_RELEASES_URL})."
        )
    return True


def _prompt_authorization_dialog(parent=None) -> bool:
    owns_root = False
    if parent is None:
        dialog = tk.Tk()
        owns_root = True
    else:
        dialog = tk.Toplevel(parent)
        dialog.transient(parent)

    dialog.title("Business Budget AI — Security Verification")
    dialog.resizable(False, False)
    dialog.configure(bg="#f4f6f4")

    width, height = 520, 420
    screen_w = dialog.winfo_screenwidth()
    screen_h = dialog.winfo_screenheight()
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2)
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    dialog.attributes("-topmost", True)

    frame = ttk.Frame(dialog, padding=(24, 20))
    frame.pack(fill="both", expand=True)

    title_label = ttk.Label(
        frame,
        text="Administrator Authorization Required",
        font=("Segoe UI Semibold", 14),
        foreground="#18221f"
    )
    title_label.pack(anchor="w", pady=(0, 4))

    subtitle = ttk.Label(
        frame,
        text=(
            "If you are not an admin, please download this file via the installer.\n\n"
            "This copy was launched from a Git repository or uninstalled source tree. "
            "Running from source code is restricted to authorized administrators. "
            "Official users should install and run Business Budget AI using the Windows installer, "
            "which runs without requiring a password."
        ),
        wraplength=470,
        font=("Segoe UI", 9),
        foreground="#374151",
        justify="left"
    )
    subtitle.pack(anchor="w", pady=(0, 10))

    installer_link_btn = ttk.Button(
        frame,
        text="🌐 Download via Installer (Official Releases)",
        command=open_installer_page
    )
    installer_link_btn.pack(anchor="w", pady=(0, 14))

    pwd_label = ttk.Label(frame, text="Administrator Password:", font=("Segoe UI Semibold", 10))
    pwd_label.pack(anchor="w", pady=(0, 4))

    password_var = tk.StringVar()
    pwd_entry = ttk.Entry(frame, textvariable=password_var, show="*", font=("Segoe UI", 11), width=40)
    pwd_entry.pack(fill="x", pady=(0, 8))
    pwd_entry.focus_set()

    remember_var = tk.BooleanVar(value=True)
    remember_check = ttk.Checkbutton(
        frame,
        text="Remember authorization on this computer",
        variable=remember_var
    )
    remember_check.pack(anchor="w", pady=(0, 10))

    status_var = tk.StringVar(value="")
    status_label = ttk.Label(frame, textvariable=status_var, font=("Segoe UI", 9), foreground="#dc2626")
    status_label.pack(anchor="w", pady=(0, 8))

    result = {"authorized": False}
    attempts = {"count": 0}

    def on_submit(_event=None):
        entered = password_var.get()
        if verify_admin_password(entered):
            if remember_var.get():
                remember_device_authorization()
            result["authorized"] = True
            dialog.destroy()
        else:
            attempts["count"] += 1
            remaining = 3 - attempts["count"]
            if remaining <= 0:
                messagebox.showerror(
                    "Access Denied",
                    "Access Denied.\n\n"
                    "If you are not an admin, please download this file via the installer.\n\n"
                    "Opening the official installer page in your web browser...",
                    parent=dialog
                )
                open_installer_page()
                dialog.destroy()
            else:
                status_var.set(
                    f"Incorrect administrator password. {remaining} attempt(s) remaining.\n"
                    "If you are not an admin, please download this file via the installer."
                )
                password_var.set("")
                pwd_entry.focus_set()

    def on_cancel():
        dialog.destroy()

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(fill="x", pady=(6, 0))

    installer_btn = ttk.Button(
        btn_frame,
        text="Installer Page",
        command=open_installer_page
    )
    installer_btn.pack(side="left")

    exit_btn = ttk.Button(btn_frame, text="Cancel & Exit", command=on_cancel)
    exit_btn.pack(side="right", padx=(8, 0))

    unlock_btn = ttk.Button(btn_frame, text="Unlock Application", command=on_submit, style="Primary.TButton")
    unlock_btn.pack(side="right")

    dialog.bind("<Return>", on_submit)
    dialog.bind("<Escape>", lambda _e: on_cancel())

    if owns_root:
        dialog.mainloop()
    else:
        dialog.grab_set()
        dialog.wait_window()

    return result["authorized"]


# Automatic startup integrity check
try:
    ensure_integrity_module()
except Exception:
    pass


if __name__ == "__main__":
    if "--revoke" in sys.argv or "--logout" in sys.argv:
        print("=" * 55)
        print("  Business Budget AI — Security Manager")
        print("=" * 55)
        if revoke_device_authorization():
            print("[SUCCESS] Admin authorization successfully removed from this PC.")
            print("Next launch will require the administrator password.")
        else:
            print("[INFO] No active authorization found or already removed.")
        print("=" * 55)
        sys.exit(0)

    force = "--repair" in sys.argv or "-r" in sys.argv
    print("=" * 55)
    print("  Business Budget AI — Security & Integrity Watchdog")
    print("=" * 55)
    root = Path(__file__).resolve().parent
    int_file = root / "integrity.py"
    if not int_file.exists():
        print("integrity.py: MISSING")
    else:
        sha = hashlib.sha256(int_file.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        print(f"integrity.py SHA256: {sha}")

    if force or not int_file.exists():
        print("\nRepairing integrity.py...")
        if repair_integrity_module(force=True):
            print("[SUCCESS] integrity.py has been restored.")
        else:
            print("[FAILED] Could not restore integrity.py.")
    else:
        ok = ensure_integrity_module()
        print(f"\nIntegrity watchdog status: {'HEALTHY' if ok else 'ALERT'}")
        print("To force repair integrity.py, run:")
        print("    python security.py --repair")
    print("=" * 55)
