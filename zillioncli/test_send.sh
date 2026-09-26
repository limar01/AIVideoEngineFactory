#!/bin/bash
# Ipatakbo ang zion-send nang unbuffered para makita ang progreso sa file output
export PATH="$HOME/.local/bin:$PATH"
cd "$HOME"
python3 -u "$HOME/.local/bin/zion-send" "Test: anong 3 beses 7, basta magic?" 2>&1
