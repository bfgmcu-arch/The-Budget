import hashlib
import hmac
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, ttk

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
    if os.environ.get("BUDGET_AI_TEST_CLEAN_DEVICE") == "1":
        return False
    try:
        token = keyring.get_password(_SERVICE_NAME, _AUTH_KEY_NAME)
        if token:
            expected = hashlib.sha256(_K_SALT + _K_VERIFIER).hexdigest()
            return hmac.compare_digest(token, expected)
    except Exception:
        pass
    return False


def remember_device_authorization():
    if os.environ.get("BUDGET_AI_TEST_CLEAN_DEVICE") == "1":
        return False
    try:
        token = hashlib.sha256(_K_SALT + _K_VERIFIER).hexdigest()
        keyring.set_password(_SERVICE_NAME, _AUTH_KEY_NAME, token)
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
            print("\n[Business Budget AI - Security Verification]")
            print("Cloned repository detected. Administrator password required to run from source.")
            entered = getpass.getpass("Administrator Password: ")
            if verify_admin_password(entered):
                remember_device_authorization()
                res = True
            else:
                print("Access denied: Incorrect administrator password.")
                res = False
        except Exception:
            res = False

    if res:
        _IS_RUNTIME_AUTHORIZED = True
    return bool(res)


def enforce_runtime_authorization(parent=None) -> bool:
    """Enforces runtime authorization across all application modules.

    If running inside an uninstalled or cloned repository, checks for device
    authorization or prompts for administrator verification. Raises PermissionError
    if unverified.
    """
    global _IS_RUNTIME_AUTHORIZED
    if _IS_RUNTIME_AUTHORIZED:
        return True
    if not require_launch_authorization(parent=parent):
        raise PermissionError(
            "Access Denied: Business Budget AI requires administrator authorization to run from an uninstalled source repository."
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

    width, height = 500, 360
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
        text="Cloned Repository Detected",
        font=("Segoe UI Semibold", 14),
        foreground="#18221f"
    )
    title_label.pack(anchor="w", pady=(0, 4))

    subtitle = ttk.Label(
        frame,
        text=(
            "This copy was launched from a Git repository or uninstalled source tree. "
            "To run the application from source, enter the administrator password.\n\n"
            "Official end users: please run the official Windows installer (BusinessBudgetAISetup.exe) "
            "which runs without requiring a password."
        ),
        wraplength=450,
        font=("Segoe UI", 9),
        foreground="#4b5563",
        justify="left"
    )
    subtitle.pack(anchor="w", pady=(0, 16))

    pwd_label = ttk.Label(frame, text="Administrator Password:", font=("Segoe UI Semibold", 10))
    pwd_label.pack(anchor="w", pady=(0, 4))

    password_var = tk.StringVar()
    pwd_entry = ttk.Entry(frame, textvariable=password_var, show="*", font=("Segoe UI", 11), width=40)
    pwd_entry.pack(fill="x", pady=(0, 10))
    pwd_entry.focus_set()

    remember_var = tk.BooleanVar(value=True)
    remember_check = ttk.Checkbutton(
        frame,
        text="Remember authorization on this computer",
        variable=remember_var
    )
    remember_check.pack(anchor="w", pady=(0, 14))

    status_var = tk.StringVar(value="")
    status_label = ttk.Label(frame, textvariable=status_var, font=("Segoe UI", 9), foreground="#dc2626")
    status_label.pack(anchor="w", pady=(0, 10))

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
                    "Too many failed password attempts. The application will now exit.",
                    parent=dialog
                )
                dialog.destroy()
            else:
                status_var.set(f"Incorrect administrator password. {remaining} attempt(s) remaining.")
                password_var.set("")
                pwd_entry.focus_set()

    def on_cancel():
        dialog.destroy()

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(fill="x", pady=(6, 0))

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
