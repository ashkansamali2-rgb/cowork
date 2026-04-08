# COWORK — Project Context & Roadmap
**Last updated:** April 8, 2026  
**Author:** Ashkan Samali  
**Machine:** MacBook Pro (Apple Silicon)  
**Status:** Phase 2 complete, Phase 3 in progress

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
│  - Cantivia (coding tasks)          │
│  - Shell tools (open apps, files)   │
│  - Ollama brain (jarvis-brain 23GB) │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│         CANTIVIA BUS                │
│  WebSocket hub — port 8002          │
│  Pub/sub event routing              │
│  Events: TASK_CODING, TASK_VOICE,   │
│  HEARTBEAT, AGENT_SPAWN, SCREENSHOT │
└──────┬───────────────────┬──────────┘
       ↓                   ↓
┌──────────────┐   ┌───────────────────┐
│ GEMMA 4 E4B  │   │  QWEN 3.5 9B      │
│ Architect    │   │  Editor           │
│ port 8080    │   │  port 8081        │
│ Plans tasks  │   │  Writes the code  │
└──────────────┘   └───────────────────┘
```

### Key Files
| File | Purpose |
|---|---|
| `~/jarvis/api_server.py` | WebSocket server, entry point |
| `~/jarvis/core/router.py` | Keyword router, brain of Jarvis |
| `~/jarvis/core/bus_client.py` | Jarvis ↔ Bus connection |
| `~/cantivia-bus.py` | Central event bus |
| `~/cantivia-cli.py` | Coding agent (Gemma + Qwen pipeline) |
| `~/jarvis/config.py` | All URLs, keys, paths |
| `~/Downloads/gemma-4-E4B-it-UD-Q6_K_XL.gguf` | Architect model |
| `~/Downloads/Qwen3.5-9B-UD-Q6_K_XL.gguf` | Editor model |

### Ports
| Port | Service |
|---|---|
| 8001 | Jarvis WebSocket API |
| 8002 | Cantivia Event Bus |
| 8080 | llama-server — Gemma 4 (Architect) |
| 8081 | llama-server — Qwen 3.5 (Editor) |
| 11434 | Ollama (jarvis-brain fallback) |

### LaunchD Services (auto-start on login)
- `com.jarvis.api` — Jarvis API server
- `com.jarvis.brain` — Ollama brain
- `com.jarvis.voice` — Voice daemon
- `com.jarvis.ollama` — Ollama service
- `com.jarvis.llamaserver` — llama.cpp server

---

## Models

| Model | File | Use |
|---|---|---|
| Gemma 4 E4B | `gemma-4-E4B-it-UD-Q6_K_XL.gguf` | Architect — planning, diagnosis |
| Qwen 3.5 9B | `Qwen3.5-9B-UD-Q6_K_XL.gguf` | Editor — writing code |
| jarvis-brain (Ollama, 23GB) | Ollama | General assistant fallback |
| Qwen3-TTS 0.6B | HuggingFace MLX | Voice output |
| Whisper large-v3-turbo | HuggingFace MLX | Voice input |

---

## Phases

---

### ✅ PHASE 1 — Foundation
**Status: Complete**

- Jarvis daemon running as launchd service
- FastAPI WebSocket server on port 8001
- Keyword router (claude code / openclaw / shell tools)
- Rolling conversation memory (10 messages)
- Basic TTS + Whisper voice pipeline (slow, needs replacement)
- Ollama brain connected

---

### ✅ PHASE 2 — The Event Bus (Dual Brain)
**Status: Complete**

- Cantivia Bus live on port 8002
- Jarvis auto-connects to bus on startup
- Gemma 4 E4B running on port 8080 (Architect)
- Qwen 3.5 9B running on port 8081 (Editor)
- Cantivia CLI connected, receives TASK_CODING events
- Full pipeline proven: voice command → Jarvis → Bus → Gemma plans → Qwen codes → file saved
- `cantivia [task]` keyword routes correctly through the pipeline

---

### 🔧 PHASE 3 — Real Code Application (Aider Integration)
**Status: In progress — next up**

**Goal:** Cantivia doesn't just write code to a file — it applies it to your actual codebase using aider.

**Tasks:**
- Configure aider to use Gemma (architect) + Qwen (editor) via llama.cpp
- Cantivia CLI spawns aider as subprocess with the task and target repo
- `cantivia fix [file or feature]` → aider opens, Gemma plans, Qwen edits, diff applied
- Support repo context: user specifies working repo or Cantivia infers from open folder
- Output diff shown in terminal, auto-applied on confirmation

**How to start:**
```bash
# Test aider with local models
aider --model openai/gemma --openai-api-base http://localhost:8080/v1 --openai-api-key dummy
```

---

### 🔧 PHASE 4 — Browser Vision (Playwright + Diagnosis)
**Status: Planned**

**Goal:** `cantivia fix localhost:3000` → screenshots the page, diagnoses the bug, patches the code.

**Tasks:**
- Playwright integration in Cantivia CLI
- On browser task: launch headless Chromium, navigate to URL, screenshot
- Screenshot → base64 → sent to Gemma as vision input (Gemma 4 is multimodal)
- Gemma diagnoses the visual bug, produces a fix plan
- Qwen writes the patch, aider applies it
- Loop: re-screenshot after patch to verify fix

**Trigger keywords:** `fix localhost`, `fix [url]`, `screenshot [url] and fix`

---

### 🔧 PHASE 5 — Fast Voice (Sub-300ms Latency)
**Status: Planned**

**Goal:** Replace the slow, sloppy voice pipeline with something that feels instant.

**Problems with current voice:**
- Whisper large is slow on CPU
- TTS pipeline has too much latency
- No interruption handling
- No wake word — have to manually trigger

**Solution:**
- Wake word: Porcupine (already have Picovoice key in config) — "Hey Cowork"
- STT: Switch to Whisper tiny or base (MLX, Apple Silicon optimised) for <100ms transcription
- Brain: Gemma 4 E4B handles fast local responses (no Ollama round trip)
- TTS: Qwen3-TTS 0.6B MLX already in HuggingFace cache — wire it in
- Interruption: kill current task on new voice input (kill switch already built)
- Target: wake word → response playing in under 1 second

---

### 🔧 PHASE 6 — Hand Gesture Control (MacBook Camera)
**Status: Planned — ambitious**

**Goal:** Control the OS with hand gestures via the built-in MacBook camera.

**Tasks:**
- MediaPipe Hands — real-time hand landmark detection (runs on CPU/ANE, no GPU needed)
- Define gesture vocabulary:
  - ✋ Open palm → pause/stop current task
  - 👆 Point → move cursor
  - 👌 Pinch → click
  - 🤏 Pinch + drag → drag windows
  - ✌️ Two fingers up → trigger voice listen mode
  - 👊 Fist → kill current agent task
- Overlay HUD: semi-transparent gesture indicator on screen (like a radar)
- Gesture events published to the bus as `GESTURE_EVENT` type
- Jarvis router handles gesture events same as voice commands

**Stack:** MediaPipe + OpenCV + PyAutoGUI for cursor control + AppKit for window management

---

### 🔧 PHASE 7 — Multi-Agent Spawner
**Status: Planned**

**Goal:** Say one thing, spawn multiple parallel agents working simultaneously.

**Example:** `"cantivia refactor the auth module and fix the dashboard layout and update the tests"`
→ 3 agents spawn in parallel, each working on one task, results merged

**Tasks:**
- `AGENT_SPAWN` event type already in bus protocol — wire it up
- Agent pool: max 3 concurrent (limited by VRAM/RAM)
- Each agent gets its own aider subprocess + model context
- Results aggregated and reported back via TASK_VOICE
- Conflict detection: if two agents edit the same file, queue them

---

### 🔧 PHASE 8 — The HUD (Ambient UI)
**Status: Planned — ambitious**

**Goal:** A always-on ambient display that shows system state without being in the way.

**Design:** Thin neon overlay on the right edge of screen (like Jarvis from the films)
- Active agents and their status
- Current voice/gesture mode indicator  
- Model inference speed (tokens/sec)
- Bus event stream (last 5 events)
- Quick actions (tap to spawn common tasks)

**Stack:** Electron (already in your setup) + CSS animations + WebSocket to bus

---

### 🔧 PHASE 9 — Self-Healing & Autonomous Loops
**Status: Future**

**Goal:** System monitors itself and fixes its own problems.

- Heartbeat engine watches all services (bus, llama servers, Jarvis)
- If a service dies → auto-restart via launchctl
- If a model produces bad output → retry with different temperature
- Nightly: auto-pull latest model updates, run self-test suite
- Error logs → Gemma diagnoses → opens GitHub issue or fixes inline

---

## How To Start The Full System

```bash
# One command to rule them all (add to ~/.zshrc as alias)
alias start="launchctl start com.jarvis.api && \
  llama-server -m ~/Downloads/gemma-4-E4B-it-UD-Q6_K_XL.gguf --port 8080 --ctx-size 8192 --n-gpu-layers 99 & \
  llama-server -m ~/Downloads/Qwen3.5-9B-UD-Q6_K_XL.gguf --port 8081 --ctx-size 8192 --n-gpu-layers 99 & \
  python3 ~/cantivia-bus.py & \
  python3 ~/cantivia-cli.py &"
```

---

## Current Limitations / Known Issues

- Voice pipeline is slow — Whisper large on CPU, high latency (Phase 5 fixes this)
- Cantivia saves to `cantivia_output.py` but doesn't apply to real files yet (Phase 3 fixes this)
- No wake word — must manually type or trigger (Phase 5 fixes this)
- Jarvis brain (Ollama 23GB) is slow for general tasks — Gemma 4 should replace it (Phase 3)
- No visual feedback when agents are working (Phase 8 fixes this)
- `on_event` deprecation warning in FastAPI — migrate to lifespan handlers (minor, cosmetic)

---

## How To Give This To Another Model

Paste this file as context. Then say:

> "Read CONTEXT.md. We are on Phase [X]. The last thing we did was [Y]. Continue from there."

The model will have everything it needs: architecture, file paths, ports, model names, current state, and what to build next.

---

## Guiding Principles

1. **Local first.** Nothing leaves the machine unless explicitly asked.
2. **No gimmicks.** Every feature must save real time in the real workflow.
3. **One command.** The whole system starts with one word.
4. **Ambient, not intrusive.** The UI should feel like Iron Man's HUD, not another app to manage.
5. **Self-healing.** If something breaks, the system fixes itself before the developer notices.
