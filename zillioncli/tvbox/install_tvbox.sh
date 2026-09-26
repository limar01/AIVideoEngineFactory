#!/bin/bash
# Zillion TVBox Edition 1-Click Installer
echo "⚡ Installing Zillion TVBox Edition (Android TV / Armbian / Linux Box)..."
mkdir -p ~/.zion ~/bin
python3 -m pip install --upgrade pip websocket-client urllib3 colorama 2>/dev/null || true
echo "✔ Zillion TVBox Edition Ready! Run ./start_tvbox.sh to launch."
