#!/bin/bash

echo "========================================"
echo "    INITIATING JARVIS BOOT SEQUENCE"
echo "========================================"

# 1. Clean the slate (Kill old Brains and APIs)
lsof -ti:8001 | xargs kill -9 2>/dev/null
lsof -ti:8080 | xargs kill -9 2>/dev/null
killall llama-server 2>/dev/null

# 2. Force 100% Offline Mode
export HF_HUB_OFFLINE=1

# 3. Boot the 9B Brain (LLM Server)
echo "[System] Igniting 9B Neural Engine..."
llama-server -m ~/Downloads/Qwen3.5-9B-UD-Q6_K_XL.gguf -c 8192 --port 8080 > /dev/null 2>&1 &
LLAMA_PID=$!

# Give the 9B brain 3 seconds to fully load into RAM before connecting the Nervous System
sleep 3

# 4. Boot the Nervous System (API Server)
echo "[System] Spooling up the Routing Network..."
cd ~/jarvis
source .venv/bin/activate
python3 api_server.py > /dev/null 2>&1 &
API_PID=$!

# 5. Boot the UI (Physically pops open a new window)
echo "[System] Connecting Mission Control UI..."
UI_DIR=$(find ~/jarvis -name "package.json" -not -path "*/node_modules/*" -not -path "*/.venv/*" -exec dirname {} \; | head -n 1)
if [ ! -z "$UI_DIR" ]; then
    osascript -e "tell application \"Terminal\" to do script \"cd '$UI_DIR' && npm start\""
else
    echo "[!] Warning: Could not find UI folder."
fi

# 6. Hardware Interlock (Ensures everything dies when you press Ctrl+C)
trap "echo -e '\n[System] Shutting down JARVIS facility...'; kill -9 $API_PID $LLAMA_PID 2>/dev/null; killall llama-server 2>/dev/null; exit" SIGINT SIGTERM

# 7. Boot the Ears (Microphone)
echo "[System] Activating Audio Subsystems..."
cd ~/jarvis
python3 interfaces/voice/live_voice.py
