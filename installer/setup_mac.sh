#!/usr/bin/env bash
# ==============================================================================
#  Abel — macOS Installer & Automated Setup
#  Property of Student Led Business Solutions
# ==============================================================================

set -e

echo "=========================================================="
echo "  Abel — macOS Installer"
echo "  Property of Student Led Business Solutions"
echo "=========================================================="
echo ""

# Determine source directory (where this script is located or parent)
SOURCE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
INSTALL_DIR="/Applications/Abel.app"
USER_INSTALL_DIR="$HOME/Applications/Abel.app"

# Choose install directory based on write permissions
TARGET_APP="$INSTALL_DIR"
if [ ! -w "/Applications" ] && [ "$EUID" -ne 0 ]; then
    mkdir -p "$HOME/Applications"
    TARGET_APP="$USER_INSTALL_DIR"
fi

echo "Target Installation: $TARGET_APP"
echo ""

# ------------------------------------------------------------------------------
# 1. Detect / Verify Python 3
# ------------------------------------------------------------------------------
echo "Checking Python 3 environment..."
PYTHON_BIN=""

if command -v python3 >/dev/null 2>&1; then
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
        PYTHON_BIN="$(command -v python3)"
        echo "Found compatible Python $PY_VER at $PYTHON_BIN"
    fi
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "Compatible Python 3.10+ was not found."
    if command -v brew >/dev/null 2>&1; then
        echo "Installing Python via Homebrew..."
        brew install python@3.12
        PYTHON_BIN="$(brew --prefix)/bin/python3.12"
    else
        echo "Please install Python 3.12+ for macOS from: https://www.python.org/downloads/macos/"
        echo "Opening python.org in your browser..."
        open "https://www.python.org/downloads/macos/"
        exit 1
    fi
fi

# ------------------------------------------------------------------------------
# 2. Build macOS Application Bundle Structure
# ------------------------------------------------------------------------------
echo ""
echo "Creating macOS Application Bundle at $TARGET_APP..."
mkdir -p "$TARGET_APP/Contents/MacOS"
mkdir -p "$TARGET_APP/Contents/Resources"

# Copy application source files into bundle Resources
echo "Copying application modules..."
cp -R "$SOURCE_DIR/ai.py" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/app.py" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/budget.py" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/budget.csv" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/bookkeeping.py" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/config.py" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/desktop_app.py" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/quickbooks.py" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/shopping_api.py" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/secure_storage.py" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/security.py" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/integrity.py" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/manifest.vault" "$TARGET_APP/Contents/Resources/"
cp -R "$SOURCE_DIR/requirements.txt" "$TARGET_APP/Contents/Resources/"
[ -f "$SOURCE_DIR/start_abel.sh" ] && cp "$SOURCE_DIR/start_abel.sh" "$TARGET_APP/Contents/Resources/"

# ------------------------------------------------------------------------------
# 3. Create Virtual Environment & Install Dependencies
# ------------------------------------------------------------------------------
echo ""
echo "Setting up application Python environment..."
VENV_DIR="$TARGET_APP/Contents/Resources/.venv"
"$PYTHON_BIN" -m venv "$VENV_DIR"
VENV_PYTHON="$VENV_DIR/bin/python"

echo "Installing required packages..."
"$VENV_PYTHON" -m pip install --upgrade pip --quiet
"$VENV_PYTHON" -m pip install -r "$TARGET_APP/Contents/Resources/requirements.txt" --quiet

# ------------------------------------------------------------------------------
# 4. Generate Authorized Installer Signature
# ------------------------------------------------------------------------------
echo ""
echo "Authorizing installation signature..."
"$VENV_PYTHON" -c "
import hashlib, hmac
k = bytes.fromhex('7a4c9b2e81d053f7a62e4c19b83d70ef')
p = bytes.fromhex('3f9a1c8b2e5d7041a8b9c2e3f4a5b6c7')
sig = hmac.new(k, p, hashlib.sha256).hexdigest()
with open('$TARGET_APP/Contents/Resources/.install_signature', 'w') as f:
    f.write(sig)
"

# ------------------------------------------------------------------------------
# 5. Create macOS Executable Wrapper (Contents/MacOS/Abel)
# ------------------------------------------------------------------------------
cat << 'EOF' > "$TARGET_APP/Contents/MacOS/Abel"
#!/usr/bin/env bash
BUNDLE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
RESOURCES_DIR="$BUNDLE_DIR/Resources"
VENV_PYTHON="$RESOURCES_DIR/.venv/bin/python"

cd "$RESOURCES_DIR"
exec "$VENV_PYTHON" "$RESOURCES_DIR/app.py" "$@"
EOF
chmod +x "$TARGET_APP/Contents/MacOS/Abel"

# ------------------------------------------------------------------------------
# 6. Create Contents/Info.plist
# ------------------------------------------------------------------------------
cat << 'EOF' > "$TARGET_APP/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
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
    <key>CFBundleExecutable</key>
    <string>Abel</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
</dict>
</plist>
EOF

# Clear quarantine attribute if on macOS
if command -v xattr >/dev/null 2>&1; then
    xattr -cr "$TARGET_APP" 2>/dev/null || true
fi

# ------------------------------------------------------------------------------
# 7. Check / Setup Ollama AI Engine
# ------------------------------------------------------------------------------
echo ""
echo "Checking Ollama local AI engine..."
if command -v ollama >/dev/null 2>&1; then
    echo "Ollama is installed."
    # Ensure Ollama service is running
    if ! pgrep -x "ollama" >/dev/null; then
        echo "Starting Ollama background server..."
        ollama serve >/dev/null 2>&1 &
        sleep 3
    fi
    echo "Verifying AI model (qwen2.5:0.5b)..."
    ollama pull qwen2.5:0.5b || true
else
    echo "Ollama is not yet installed."
    if command -v brew >/dev/null 2>&1; then
        echo "Installing Ollama via Homebrew..."
        brew install ollama
        ollama serve >/dev/null 2>&1 &
        sleep 3
        ollama pull qwen2.5:0.5b || true
    else
        echo "Tip: You can download Ollama for macOS at https://ollama.com/download/mac"
    fi
fi

echo ""
echo "=========================================================="
echo "  Installation Successful!"
echo "  Abel is ready at: $TARGET_APP"
echo "  Property of Student Led Business Solutions"
echo "=========================================================="
echo ""

# Ask to launch
read -p "Would you like to launch Abel now? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    open "$TARGET_APP"
fi
