# COWORK — Project Context & Roadmap
**Last updated:** April 11, 2026
**Author:** Ashkan Samali
**Machine:** MacBook Pro (Apple Silicon)
**Status:** Phase 7 complete, Phase 8 in progress

---

## What This Is

A fully local, voice + gesture controlled AI operating system for a solo developer.
No subscriptions. No cloud dependency. No gimmicks.

The goal: replace the current workflow of juggling Claude web + Gemini + Antigravity + Claude Code CLI
with a single unified system that listens, sees, codes, and acts — running entirely on-device.

Think Iron Man's JARVIS. Not a chatbot. An operating system you talk to.

---

## Current Workflow (What We're Replacing)

| Tool | Role | Problem |
|---|---|---|
| Claude Web (Sonnet) | Main brain, gives code | Have to copy/paste to editor |
| Gemini | Consultant / second opinion | Manual, separate tab |
| Antigravity | Code editor | Have to manually paste Claude's output |
| Claude Code CLI | Applies code to files | Eats Claude usage quota fast |
| Terminal (manual) | Running everything | Too many windows, too much friction |

**The replacement:** Say or gesture a task → system plans it → writes it → applies it to your actual files → done.

---

## System Architecture (Current State)

```
You (voice / text / gesture)
        ↓
┌─────────────────────────────────────┐
│         JARVIS DAEMON               │
│  FastAPI WebSocket — port 8001      │
│  Keyword router → branches to:      │
│  - Fast routes (time/date/battery)  │
│  - Cantivia (coding tasks)          │
│  - Shell tools (open apps, files)   │
│  - Qwen 9B brain (llama.cpp)        │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│         CANTIVIA BUS                │
│  WebSocket hub — port 8002          │
│  Pub/sub event routing              │
│  Events: TASK_CODING, TASK_VOICE,   │
│  HEARTBEAT, AGENT_SPAWN, SCREENSHOT │
│  Daily rotating logs: ~/cowork/logs/│
└──────┬───────────────────┬──────────┘
       ↓                   ↓
┌──────────────┐   ┌───────────────────┐
│ GEMMA 4 E4B  │   │  QWEN 3.5 9B      │
│ Architect    │   │  Editor + Brain   │
│ port 8080    │   │  port 8081        │
│ Plans tasks  │   │  Writes the code  │
└──────────────┘   └───────────────────┘
```

---

## Services & Ports

| Port | Service | Description |
|---|---|---|
| 8001 | Jarvis WebSocket API | Main entry point — handles voice, text, routes all commands |
| 8002 | Cantivia Event Bus | WebSocket pub/sub hub; routes events between Jarvis and Cantivia CLI |
| 8080 | llama-server — Gemma 4 E4B | Architect model; plans tasks, multimodal |
| 8081 | llama-server — Qwen 3.5 9B | Editor model; writes code; also used as Jarvis brain |
| 5173 | Command Station (Vite dev) | Fallback when Electron app is not built |

---

## Key Files

| File | Purpose |
|---|---|
| `~/cowork/jarvis/api_server.py` | FastAPI WebSocket server, entry point for all messages |
| `~/cowork/jarvis/core/router.py` | Keyword router; fast routes, Claude Code, OpenClaw, Cantivia, LLM |
| `~/cowork/jarvis/core/bus_client.py` | Jarvis → Bus WebSocket client |
| `~/cowork/jarvis/config.py` | All URLs, keys, model paths |
| `~/cowork/cantivia-bus.py` | Central WebSocket event bus (port 8002); daily log rotation |
| `~/cowork/cantivia-cli.py` | Coding agent — Gemma plans, Qwen edits, aider applies |
| `~/cowork/start_cowork.sh` | One-command startup script; coloured status, health checks |
| `~/cowork/clap_start.py` | Double-clap listener; calls start_cowork.sh on trigger |
| `~/cowork/logs/` | Daily rotating logs: bus-YYYY-MM-DD.log, jarvis.log, etc. |
| `~/cowork/ui/command-station/` | Electron + React dashboard |
| `~/cowork/ui/command-station/dist-electron/mac-arm64/Command Station.app` | Built Electron app |
| `~/cowork/ui/cli/jarvis_cli.py` | CLI rewritten with prompt_toolkit + Rich (v0.6.0) |
| `~/cowork/vision/gesture_daemon.py` | MediaPipe gesture detection daemon |
| `~/Downloads/gemma-4-E4B-it-UD-Q6_K_XL.gguf` | Architect model file |
| `~/Downloads/Qwen3.5-9B-UD-Q6_K_XL.gguf` | Editor/brain model file |

---

## Models

| Model | File | Use |
|---|---|---|
| Gemma 4 E4B | `gemma-4-E4B-it-UD-Q6_K_XL.gguf` | Architect — planning, diagnosis, multimodal |
| Qwen 3.5 9B | `Qwen3.5-9B-UD-Q6_K_XL.gguf` | Editor — writing code; Jarvis general brain |
| Qwen3-TTS 0.6B | HuggingFace MLX | Voice output |
| Whisper large-v3-turbo | HuggingFace MLX | Voice input |

---

## Performance Improvements

- **Qwen context window:** Reduced to lower memory pressure and speed up inference
- **Model pre-warming:** Models warm-loaded on daemon startup to reduce first-response latency
- **Fast routes in router.py:** Hardcoded instant responses for greetings, app opens, common queries (time, date, battery, volume) — zero LLM overhead

---

## CLI (v0.6.0)

The CLI (`ui/cli/jarvis_cli.py`) has been fully rewritten:
- **prompt_toolkit** for interactive input with history, keybindings, and tab-completion
- **Rich** for styled terminal output (panels, tables, coloured status)
- Slash commands: `/project`, `/memory`, `/agents`, `/help`, `/clear`
- Multi-line input mode
- Persistent session history

---

## Phases

---

### PHASE 1 — Foundation
**Status: Complete**

- Jarvis daemon running as launchd service
- FastAPI WebSocket server on port 8001
- Keyword router (claude code / openclaw / shell tools)
- Rolling conversation memory (10 messages)
- Basic TTS + Whisper voice pipeline
- Ollama brain connected

---

### PHASE 2 — The Event Bus (Dual Brain)
**Status: Complete**

- Cantivia Bus live on port 8002
- Jarvis auto-connects to bus on startup
- Gemma 4 E4B running on port 8080 (Architect)
- Qwen 3.5 9B running on port 8081 (Editor)
- Cantivia CLI connected, receives TASK_CODING events
- Full pipeline proven: voice command → Jarvis → Bus → Gemma plans → Qwen codes → file saved
- `cantivia [task]` keyword routes correctly through the pipeline

---

### PHASE 3 — Aider Integration via Cantivia Pipeline
**Status: Complete**

- `AGENT_SPAWN` event type wired up end to end
- Agent pool: up to 3 concurrent aider subprocesses
- Each agent receives its own task + target file context
- CLI folder-awareness: `cwd` passed through bus events so agents know which repo to target
- Results aggregated and reported back via `TASK_VOICE`
- Projects support: named sessions with message isolation
- CLI slash commands: `/project`, `/memory`, `/agents`, etc.
- aider integrated as the code-application layer inside cantivia-cli.py

---

### PHASE 4 — Browser Vision (Playwright + Gemma Diagnosis)
**Status: Complete**

- `cantivia fix localhost:3000` → screenshots page → Gemma diagnoses visually → Qwen patches → re-screenshot to verify
- Playwright integration for browser control and screenshot capture
- Gemma 4 E4B multimodal vision used for UI diagnosis
- ForensicNet vision backbone added under `vision/backbone/ForensicNet`
- Screenshot events routed through the Cantivia bus

---

### PHASE 5 — Voice Reliability & Latency
**Status: In progress**

- Reliability fixes applied: reconnect loops, error recovery, dead-session cleanup
- Voice pipeline hardened against timeout and model load failures
- Wake word groundwork: "Hey Cowork" planned via Porcupine
- STT: Whisper tiny/base MLX for <100ms transcription (target)
- TTS: Qwen3-TTS 0.6B MLX
- Target: wake word → response playing in under 1 second

---

### PHASE 6 — Hand Gesture Control
**Status: Planned** (`gesture_daemon.py` exists)

- `vision/gesture_daemon.py` scaffolded and ready
- MediaPipe Hands real-time gesture detection via MacBook camera
- Gestures: open palm (stop), point (cursor), pinch (click), two fingers (voice mode), fist (kill agent)
- Gesture events published to bus as `GESTURE_EVENT`

---

### PHASE 7 — Multi-Agent System
**Status: Complete**

- Full multi-agent orchestration implemented
- Agents spawned dynamically from bus events
- Agent lifecycle: spawn → task assignment → heartbeat → result → cleanup
- Loop detection: agents self-terminate on repeated identical outputs
- Agent panel in Command Station HUD shows live agent status
- Multitasking: multiple agents run concurrently on different tasks/repos
- Agent results aggregated and spoken back via TTS
- Reliability: agents track their own state, handle timeouts gracefully

---

### PHASE 8 — The HUD (Ambient UI)
**Status: In progress**

- Corner dot implemented: always-visible ambient indicator in screen corner
- Shows active state (listening / processing / idle) via colour
- Full HUD planned: always-on thin neon overlay with active agents, voice mode, inference speed, bus event stream
- Stack: Electron + CSS animations + WebSocket to bus
- HUD voice-only mode available

---

### PHASE 9 — Self-Healing & Autonomous Loops
**Status: Future**

- Heartbeat engine watches all services; auto-restart via launchctl
- Nightly: model updates, self-test suite
- Error logs → Gemma diagnoses → fix inline or open GitHub issue

---

## How To Start The Full System

```bash
# One command
~/cowork/start_cowork.sh

# Or double-clap (with clap_start.py running in background)
python3 ~/cowork/clap_start.py
```

Logs land in `~/cowork/logs/`.

---

## Current Known Issues Being Fixed

| Issue | Fix |
|---|---|
| "open chrome" fails — wrong app name | APP_NAME_MAP normalisation in router.py |
| "what time is it" hits LLM unnecessarily | Fast hardcoded routes, returns in <1ms |
| Bus logs scattered, no file persistence | Daily rotating log files in ~/cowork/logs/ |
| Starting system requires multiple terminal commands | start_cowork.sh with health checks |
| clap_start.py duplicated startup logic | Now delegates entirely to start_cowork.sh |
| Voice pipeline drops connection under load | Reconnect loops + error recovery in voice layer |
| Agent loop detection missing | Agents now self-terminate on repeated output |
| HUD not visible | Corner dot implemented as minimal ambient indicator |

---

## Guiding Principles

1. **Local first.** Nothing leaves the machine unless explicitly asked.
2. **No gimmicks.** Every feature must save real time in the real workflow.
3. **One command.** The whole system starts with one word.
4. **Ambient, not intrusive.** The UI should feel like Iron Man's HUD, not another app to manage.
5. **Self-healing.** If something breaks, the system fixes itself before the developer notices.

---

## How To Give This To Another Model

Paste this file as context. Then say:

> "Read CONTEXT.md. We are on Phase [X]. The last thing we did was [Y]. Continue from there."
