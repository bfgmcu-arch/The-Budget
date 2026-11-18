#!/usr/bin/env bash
# Abel — Property of Student Led Business Solutions
# Universal Unix/macOS Launcher

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Check for virtual environment Python
if [ -f "$DIR/.venv/bin/python" ]; then
    PYTHON_EXE="$DIR/.venv/bin/python"
elif [ -f "$DIR/Contents/Resources/.venv/bin/python" ]; then
    PYTHON_EXE="$DIR/Contents/Resources/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_EXE="$(command -v python3)"
else
    echo "ERROR: Python 3 is required to run Abel."
    echo "Please run Install_Abel.command or install Python 3."
    exit 1
fi

exec "$PYTHON_EXE" "$DIR/app.py" "$@"
