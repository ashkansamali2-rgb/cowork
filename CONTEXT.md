# Cowork Jarvis Ecosystem — System Context

## Architecture Overview
The Cowork system is a multi-agent AI infrastructure deeply integrated into macOS. It fuses background autonomous processing with multi-modal real-time interaction (Voice, Desktop UI).

### Core Services
1. **Llama Backends (Backend LLMs)**
   - **E4B Fast Model** (Port `8080`): Handling voice inputs and simple `<100 token` queries. Model: `gemma-4-E4B-it-UD-Q6_K_XL.gguf`.
   - **31B Heavy Model** (Port `8081`): Handling deep reasoning, coding requests, and hierarchical architecture. Model: `gemma-4-31B-it-IQ4_NL.gguf`.
2. **Jarvis API Core** (Port `8001`): FastAPI edge orchestrating context, websockets, memory, and LLM routes. 
3. **Cantivia Bus** (Port `8002`): RabbitMQ-style lightweight message broker routing coding instructions to Cantivia CLI pipelines.
4. **Command Station** (Vite Dev Server `5173`): Real-time live React monitoring dashboard capable of analyzing dynamic background tools and knowledge graphs.

## Interfaces
- **Voice Pipeline**: Driven by `jarvis/interfaces/voice/live_voice.py`. Independent async STT/WS/TTS routines ensure instantaneous auditory execution leveraging `mlx-whisper-large-v3-turbo-q4` for parsing and `Qwen3-TTS` for rendering.
- **HUD**: Electron overlay written cleanly using native websockets ensuring zero-latency transparent screen updates indicating backend AI thinking or responses.
- **CLI Terminal**: Built on `prompt_toolkit` + `rich`. Simulating a clean, professional "Claude Code" type experience, trapping local `/` commands but forwarding complex instructions (e.g. `cantivia <prompt>`) natively to the background bus.

## Autonomy & Agents
Background agents execute via the `AgentRuntime` subsystem using React loops:
- Tool executions are localized natively through MacOS commands (`<cmd>`).
- Subagent hierarchical spawning is handled by Architect (planning) and Engineer (executors).
- Nightly meta-agent builds provide autonomous self-improvement loops targeting project structural enhancements.

## Start Sequence (`~/.zshrc`)
The unified `start` alias correctly builds the hierarchy:
1. Clears environment ports.
2. Inits Llama 8080 and 8081 models (waits 90s for memory to load).
3. Inits API server, Bus, and CLI.
4. Starts Voice Daemon, Node HUD, and Command Station Dashboard.
5. Emits Ready sequence.

## Network Topology
- `8080`: Primary E4B Localhost Inference.
- `8081`: Secondary 31B Localhost Inference.
- `8001`: Primary Jarvis router Websocket loop.
- `8002`: Secondary Cantivia internal BUS messaging.
- `5173`: Command station UI.
