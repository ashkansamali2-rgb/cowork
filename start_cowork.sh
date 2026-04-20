#!/bin/zsh
source ~/.zshrc

# ── Coloured output helpers ───────────────────────────────────────────────────
green()  { printf "\033[92m%s\033[0m\n" "$*"; }
yellow() { printf "\033[93m%s\033[0m\n" "$*"; }
red()    { printf "\033[91m%s\033[0m\n" "$*"; }

COWORK="/Users/ashkansamali/cowork"
JARVIS="$COWORK/jarvis"
VENV="$JARVIS/.venv/bin"
GEMMA="/Users/ashkansamali/Downloads/gemma-4-31B-it-IQ4_NL.gguf"
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
yellow "Clearing ports and orphaned processes..."
lsof -ti:8001,8002,8080,8081,5173,4001 | xargs kill -9 2>/dev/null
pkill -i -f "llama-server|aider|litellm|live_voice|api_server|cantivia|Command Station|ollama" 2>/dev/null
sleep 2

# ── 1. Cantivia Bus (Disabled for Aider stability) ──────────────────────────────
# yellow "⟳ Starting Cantivia Bus..."
# python3 "$COWORK/cantivia-bus.py" > "$COWORK/logs/bus.log" 2>&1 &
# wait_for_port 8002 10 && green "✓ Cantivia Bus ready" || red "✗ Bus failed"
# sleep 2

# ── 3. Gemma 4 31B — Core API model (port 8081) ──────────────────────────────
yellow "⟳ Starting Gemma 4 31B (Core)..."
MODEL_31B="/Users/ashkansamali/Downloads/gemma-4-31B-it-IQ4_NL.gguf"
/opt/homebrew/bin/llama-server -m "$MODEL_31B" --port 8081 -c 16384 --n-gpu-layers 99 --mlock \
    --batch-size 128 --threads 8 --parallel 1 \
    > "$COWORK/logs/gemma.log" 2>&1 &
wait_for_port 8081 30 && green "✓ Gemma 4 31B ready" || red "✗ Model failed"
sleep 5

# ── 3.5 LiteLLM Proxy (port 4001) ─────────────────────────────────────────────
yellow "⟳ Starting LiteLLM proxy..."
nohup /Users/ashkansamali/cowork/venv/bin/litellm --config /Users/ashkansamali/cowork/litellm_proxy.yaml --port 4001 > /tmp/proxy.log 2>&1 &
wait_for_port 4001 10 && green "✓ LiteLLM ready" || red "✗ Proxy failed"
sleep 2

# ── 4. Jarvis API server (port 8001) ─────────────────────────────────────────
yellow "⟳ Starting Jarvis API..."
"$VENV/python3" "$JARVIS/api_server.py" > "$COWORK/logs/jarvis.log" 2>&1 &
wait_for_port 8001 10 && green "✓ Jarvis API ready" || red "✗ Jarvis failed"
sleep 1

# ── 5. Cantivia CLI (Disabled for Aider stability) ─────────────────────────────
# yellow "⟳ Starting Cantivia CLI..."
# "$VENV/python3" "$COWORK/cantivia-cli.py" > "$COWORK/logs/cantivia-cli.log" 2>&1 &
# wait_for_proc "cantivia-cli" 10 && green "✓ Cantivia CLI ready" || red "✗ CLI failed"
# sleep 1

# ── 6. Live Voice (Disabled) ──────────────────────────────────────────────────
# yellow "⟳ Starting voice pipeline..."
# "$VENV/python3" "$JARVIS/interfaces/voice/live_voice.py" > "$COWORK/logs/voice.log" 2>&1 &
# if wait_for_proc "live_voice" 10; then
#     green "✓ Voice pipeline ready"
# else
#     red "✗ Voice pipeline failed — check $COWORK/logs/voice.log"
# fi

# ── 7. Command Station ────────────────────────────────────────────────────────
# Always start Vite server using absolute npm path
yellow "⟳ Starting Command Station UI (Vite)..."
nohup /opt/homebrew/bin/npm --prefix "$COWORK/ui/command-station" run dev > "$COWORK/logs/commandstation.log" 2>&1 &

if wait_for_port 5173 30; then
    if [ -d "$ELECTRON_APP" ]; then
        open "$ELECTRON_APP"
        green "✓ Command Station UI + Electron App ready"
    else
        open "http://localhost:5173"
        green "✓ Command Station UI ready at http://localhost:5173"
    fi
else
    red "✗ Command Station failed to start Vite server — check $COWORK/logs/commandstation.log"
fi

green ""
green "  Cowork is up (Core Services: Model + Bus + API + CLI)."
green "  Logs: $COWORK/logs/"
