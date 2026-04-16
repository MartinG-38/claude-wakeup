#!/bin/zsh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Try python3 first, then fall back to python for systems where the command
# name is different.
if command -v python3 >/dev/null 2>&1; then
  python3 claude_wakeup_gui.py
  osascript -e 'tell application "Terminal" to close front window' >/dev/null 2>&1 &
elif command -v python >/dev/null 2>&1; then
  python claude_wakeup_gui.py
  osascript -e 'tell application "Terminal" to close front window' >/dev/null 2>&1 &
else
  echo "Python was not found in PATH."
  echo "Install Python 3 and try again."
  read -r "?Press Enter to close..."
fi
