#!/data/data/com.termux/files/usr/bin/bash
# Zillion Mobile CLI Installer for Android Termux
echo "⚡ Installing Zillion Phone Edition for Termux / Android..."

mkdir -p ~/.zion ~/bin
pkg update -y && pkg install -y python python-pip curl
pip install websocket-client urllib3

cp zion_phone.py ~/bin/zion
chmod +x ~/bin/zion

echo "export PATH=\$HOME/bin:\$PATH" >> ~/.bashrc
export PATH=$HOME/bin:$PATH

echo "✔ Zillion Mobile CLI installed successfully!"
echo "Run 'zion' or 'zion help' or 'python3 app_phone.py' to launch Mobile Web Hub."
