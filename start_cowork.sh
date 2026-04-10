#!/bin/zsh
source ~/.zshrc

# ── Coloured output helpers ───────────────────────────────────────────────────
green()  { printf "\033[92m%s\033[0m\n" "$*"; }
yellow() { printf "\033[93m%s\033[0m\n" "$*"; }
red()    { printf "\033[91m%s\033[0m\n" "$*"; }

COWORK="/Users/ashkansamali/cowork"
JARVIS="$COWORK/jarvis"
VENV="$JARVIS/.venv/bin"
GEMMA="$HOME/Downloads/gemma-4-E4B-it-UD-Q6_K_XL.gguf"
QWEN="$HOME/Downloads/Qwen3.5-9B-UD-Q6_K_XL.gguf"
ELECTRON_APP="$COWORK/ui/command-station/dist-electron/mac-arm64/Command Station.app"

mkdir -p "$COWORK/logs"

# ── Wait-for-port helper ──────────────────────────────────────────────────────
# wait_for_port <port> <timeout_seconds>
wait_for_port() {
    local port=$1
    local timeout=${2:-10}
    local elapsed=0
    while ! nc -z 127.0.0.1 "$port" 2>/dev/null; do
        sleep 1
        elapsed=$((elapsed + 1))
        if [ $elapsed -ge $timeout ]; then
            return 1
        fi
    done
    return 0
}

# ── Wait-for-process helper ───────────────────────────────────────────────────
# wait_for_proc <pattern> <timeout_seconds>
wait_for_proc() {
    local pattern=$1
    local timeout=${2:-10}
    local elapsed=0
    while ! pgrep -f "$pattern" >/dev/null 2>&1; do
        sleep 1
        elapsed=$((elapsed + 1))
        if [ $elapsed -ge $timeout ]; then
            return 1
        fi
    done
    return 0
}

# ── Kill anything already using these ports ───────────────────────────────────
yellow "Clearing ports 8001 8002 8080 8081 5173..."
lsof -ti:8001,8002,8080,8081,5173 | xargs kill -9 2>/dev/null
sleep 1

# ── 1. Cantivia Bus (port 8002) ───────────────────────────────────────────────
yellow "⟳ Starting Cantivia Bus..."
python3 "$COWORK/cantivia-bus.py" > "$COWORK/logs/bus.log" 2>&1 &
if wait_for_port 8002 10; then
    green "✓ Cantivia Bus ready  (port 8002)"
else
    red "✗ Cantivia Bus failed — check $COWORK/logs/bus.log"
fi

# ── 2. Gemma 4 E4B — Architect model (port 8080) ──────────────────────────────
yellow "⟳ Starting Gemma 4 (Architect)..."
llama-server -m "$GEMMA" --port 8080 --ctx-size 8192 --n-gpu-layers 99 \
    > "$COWORK/logs/gemma.log" 2>&1 &
if wait_for_port 8080 10; then
    green "✓ Gemma 4 ready  (port 8080)"
else
    red "✗ Gemma 4 failed — check $COWORK/logs/gemma.log"
fi

# ── 3. Qwen 3.5 9B — Editor model (port 8081) ────────────────────────────────
yellow "⟳ Starting Qwen 3.5 (Editor)..."
llama-server -m "$QWEN" --port 8081 --ctx-size 8192 --n-gpu-layers 99 \
    > "$COWORK/logs/qwen.log" 2>&1 &
if wait_for_port 8081 10; then
    green "✓ Qwen 3.5 ready  (port 8081)"
else
    red "✗ Qwen 3.5 failed — check $COWORK/logs/qwen.log"
fi

# ── 4. Jarvis API server (port 8001) ─────────────────────────────────────────
yellow "⟳ Starting Jarvis..."
"$VENV/python3" "$JARVIS/api_server.py" > "$COWORK/logs/jarvis.log" 2>&1 &
if wait_for_port 8001 10; then
    green "✓ Jarvis ready  (port 8001)"
else
    red "✗ Jarvis failed — check $COWORK/logs/jarvis.log"
fi

# ── 5. Cantivia CLI (coding agent) ────────────────────────────────────────────
yellow "⟳ Starting Cantivia CLI..."
"$VENV/python3" "$COWORK/cantivia-cli.py" > "$COWORK/logs/cantivia-cli.log" 2>&1 &
if wait_for_proc "cantivia-cli" 10; then
    green "✓ Cantivia CLI ready"
else
    red "✗ Cantivia CLI failed — check $COWORK/logs/cantivia-cli.log"
fi

# ── 6. Live Voice ─────────────────────────────────────────────────────────────
yellow "⟳ Starting voice pipeline..."
"$VENV/python3" "$JARVIS/interfaces/voice/live_voice.py" > "$COWORK/logs/voice.log" 2>&1 &
if wait_for_proc "live_voice" 10; then
    green "✓ Voice pipeline ready"
else
    red "✗ Voice pipeline failed — check $COWORK/logs/voice.log"
fi

# ── 7. Command Station ────────────────────────────────────────────────────────
yellow "⟳ Launching Command Station..."
if [ -d "$ELECTRON_APP" ]; then
    open "$ELECTRON_APP"
    green "✓ Command Station launched (Electron app)"
else
    # Fall back to dev server
    (cd "$COWORK/ui/command-station" && npm run dev > "$COWORK/logs/commandstation.log" 2>&1) &
    if wait_for_port 5173 10; then
        open "http://localhost:5173"
        green "✓ Command Station ready at http://localhost:5173"
    else
        red "✗ Command Station failed — check $COWORK/logs/commandstation.log"
    fi
fi

green ""
green "  Cowork is up. All services started."
green "  Logs: $COWORK/logs/"
