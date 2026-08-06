#!/bin/bash
cd ~/glitch-squad-biomedical-assistant
source venv/bin/activate
pkill -f "python app.py" 2>/dev/null
pkill -f "python3 app.py" 2>/dev/null
fuser -k 5000/tcp 2>/dev/null
sleep 1
python app.py
