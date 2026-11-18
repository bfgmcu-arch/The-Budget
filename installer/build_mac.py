"""Build macOS Application Bundle and Installer for Abel.

Property of Student Led Business Solutions.
Can be executed on Windows, Linux, or macOS to generate macOS distribution packages:
- Abel.app (macOS Application Bundle)
- Abel-macOS-Installer.zip
- Abel.dmg (when built on macOS)
"""

import hashlib
import hmac
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile


_S_KEY = bytes.fromhex("7a4c9b2e81d053f7a62e4c19b83d70ef")
_S_DATA = bytes.fromhex("3f9a1c8b2e5d7041a8b9c2e3f4a5b6c7")

CORE_PAYLOAD_FILES = [
    "ai.py",
    "app.py",
    "budget.py",
    "budget.csv",
    "bookkeeping.py",
    "config.py",
    "desktop_app.py",
    "quickbooks.py",
    "shopping_api.py",
    "secure_storage.py",
    "security.py",
    "integrity.py",
    "manifest.vault",
    "requirements.txt",
    "start_abel.sh",
]


def build_mac_bundle(root_dir=None):
    if root_dir is None:
        root_dir = Path(__file__).resolve().parent.parent
    else:
        root_dir = Path(root_dir).resolve()

    output_dir = root_dir / "installer" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    mac_stage = output_dir / "mac_build"
    if mac_stage.exists():
        shutil.rmtree(mac_stage)
    mac_stage.mkdir(parents=True, exist_ok=True)

    app_bundle = mac_stage / "Abel.app"
    contents_dir = app_bundle / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"

    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    print("Copying core files into Abel.app bundle...")
    for filename in CORE_PAYLOAD_FILES:
        src = root_dir / filename
        if src.exists():
            shutil.copy2(src, resources_dir / filename)
        else:
            print(f"Warning: file {filename} not found, skipping.")

    # Generate the official installer authorization signature
    print("Generating authorized installer signature...")
    expected_sig = hmac.new(_S_KEY, _S_DATA, hashlib.sha256).hexdigest()
    sig_path = resources_dir / ".install_signature"
    sig_path.write_text(expected_sig, encoding="utf-8")

    # Write Contents/Info.plist
    info_plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Abel</string>
    <key>CFBundleDisplayName</key>
    <string>Abel</string>
    <key>CFBundleIdentifier</key>
    <string>com.studentledbusinesssolutions.abel</string>
    <key>CFBundleVersion</key>
    <string>3.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>3.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>ABEL</string>
    <key>CFBundleExecutable</key>
    <string>Abel</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © Student Led Business Solutions. All rights reserved.</string>
</dict>
</plist>
"""
    (contents_dir / "Info.plist").write_text(info_plist, encoding="utf-8")

    # Write Contents/MacOS/Abel launcher
    launcher_script = """#!/usr/bin/env bash
BUNDLE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
RESOURCES_DIR="$BUNDLE_DIR/Resources"

# Detect Python interpreter
if [ -f "$RESOURCES_DIR/.venv/bin/python" ]; then
    PY_BIN="$RESOURCES_DIR/.venv/bin/python"
elif [ -f "$HOME/Library/Application Support/Abel/.venv/bin/python" ]; then
    PY_BIN="$HOME/Library/Application Support/Abel/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY_BIN="$(command -v python3)"
else
    osascript -e 'display alert "Abel Setup Required" message "Python 3 is required to run Abel. Please run Install_Abel.command or install Python 3."'
    exit 1
fi

cd "$RESOURCES_DIR"
exec "$PY_BIN" "$RESOURCES_DIR/app.py" "$@"
"""
    launcher_path = macos_dir / "Abel"
    launcher_path.write_text(launcher_script, encoding="utf-8", newline="\n")

    # Also copy installer scripts into package
    shutil.copy2(root_dir / "Install_Abel.command", mac_stage / "Install_Abel.command")
    mac_installer_dir = mac_stage / "installer"
    mac_installer_dir.mkdir(exist_ok=True)
    shutil.copy2(root_dir / "installer" / "setup_mac.sh", mac_installer_dir / "setup_mac.sh")

    # Create Abel-macOS-Installer.zip
    zip_output = output_dir / "Abel-macOS-Installer.zip"
    print(f"Creating zip archive at {zip_output.name}...")
    with zipfile.ZipFile(zip_output, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in mac_stage.rglob("*"):
            rel_path = file.relative_to(mac_stage)
            zf.write(file, rel_path)
            # Preserve executable bits in zip info
            if file.name in ("Abel", "Install_Abel.command", "setup_mac.sh", "start_abel.sh"):
                zinfo = zf.getinfo(str(rel_path).replace("\\", "/"))
                zinfo.external_attr = 0o755 << 16

    print(f"[SUCCESS] macOS package created: {zip_output} ({zip_output.stat().st_size:,} bytes)")

    # If running on macOS, build disk image (.dmg)
    if sys.platform == "darwin" and shutil.which("hdiutil"):
        dmg_output = output_dir / "Abel.dmg"
        print("Building Apple Disk Image (Abel.dmg)...")
        dmg_stage = output_dir / "dmg_stage"
        if dmg_stage.exists():
            shutil.rmtree(dmg_stage)
        dmg_stage.mkdir(parents=True, exist_ok=True)
        shutil.copytree(app_bundle, dmg_stage / "Abel.app")
        os.symlink("/Applications", str(dmg_stage / "Applications"))
        subprocess.run(["hdiutil", "create", "-volname", "Abel", "-srcfolder", str(dmg_stage), "-ov", "-format", "UDZO", str(dmg_output)], check=True)
        shutil.rmtree(dmg_stage)
        print(f"[SUCCESS] Apple DMG created: {dmg_output} ({dmg_output.stat().st_size:,} bytes)")

    # Cleanup temporary staging dir
    try:
        shutil.rmtree(mac_stage)
    except Exception:
        pass

    return zip_output


if __name__ == "__main__":
    build_mac_bundle()
