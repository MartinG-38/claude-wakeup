#!/bin/bash
# Sets the execute permission on the macOS launcher.
# Run this once on each Mac after cloning or syncing via cloud storage,
# which strips the execute bit from .command files.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$SCRIPT_DIR/Claude Wakeup macOS.command"

if [ ! -f "$TARGET" ]; then
    echo "Error: '$TARGET' not found."
    exit 1
fi

chmod +x "$TARGET"
echo "Done. You can now double-click 'Claude Wakeup macOS.command' to launch."
