# Jarvis System Documentation

This document outlines the architecture, services, ports, and operational commands for the Jarvis system.

## 🏛️ System Architecture

The Jarvis system is composed of several interconnected services:

1.  **API Server (`jarvis/api_server.py`):** The core backend service responsible for handling agent logic, state management, and communication with external clients. It manages WebSocket connections for real-time data streaming.
2.  **CLI Interface (`ui/cli/jarvis_cli.py`):** The command-line interface used for user interaction, monitoring, and controlling the system state. It communicates with the API server via a dedicated WebSocket bus.
3.  **Agent Monitoring UI (`ui/command-station/src/components/AgentSpawner.jsx`):** A frontend component (likely part of a larger UI) used to monitor running agents, view their status, and spawn new tasks.

**Communication Flow:**
*   User interacts with CLI or UI $\rightarrow$ Sends commands/requests to API Server.
*   API Server $\leftrightarrow$ Agent Processes (Internal logic).
*   API Server $\leftrightarrow$ CLI/UI (Real-time updates via WebSockets).

## 🔌 Ports and Services

The system utilizes the following ports and services:

| Service | Component | Protocol | Port | Description |
| :--- | :--- | :--- | :--- | :--- |
| API Server | `jarvis/api_server.py` | WebSocket | 8001 | Main entry point for agent communication and data streaming. |
| Bus WebSocket | `ui/cli/jarvis_cli.py` | WebSocket | 8002 | Dedicated bus for CLI to communicate with the API server. |
| Agent Services | Various | HTTP | 8080, 8081, 8082 | Ports used by specific agent models (Gemma, Qwen, Voice). |

## ⚙️ Commands

The following commands are available for managing the Jarvis system:

### System Control Commands (CLI)

*   **`jarvis start`**: Initializes and starts all necessary services (API Server, background workers, etc.).
*   **`jarvis stop`**: Gracefully shuts down all running services.
*   **`jarvis status`**: Reports the current operational status of all services and agents.
*   **`jarvis cli`**: Launches the interactive command-line interface for direct interaction.

### Agent Management Commands (Via CLI/UI)

*   **`agent spawn <task_description>`**: Initiates a new agent task based on the provided description.
*   **`agent list`**: Displays a list of all currently tracked agents and their statuses.
*   **`agent stop <agent_id>`**: Attempts to terminate a specific running agent.

## 🚀 Getting Started

1.  Ensure all dependencies are installed.
2.  Run `jarvis start` to bring the system online.
3.  Use `jarvis cli` or the web interface to begin interacting with Jarvis.
