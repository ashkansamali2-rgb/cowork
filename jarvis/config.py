# ============================================================
#  JARVIS CONFIG — edit this file with your settings
# ============================================================

# Ollama
OLLAMA_URL        = "http://localhost:11434"
BRAIN_MODEL = "jarvis-brain:latest"
ORCHESTRATOR_MODEL = 'jarvis-brain:latest'

# API Keys (fill these in)
ANTHROPIC_API_KEY = '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'
OPENAI_API_KEY    = ""   # only needed if you use OpenAI models

# Branches
ACTIVE_BRANCH     = "coding"   # coding | cad | general

# Paths
JARVIS_ROOT       = "/Users/ashkansamali/jarvis"
MEMORY_PATH       = "/Users/ashkansamali/jarvis/memory"
LOG_PATH          = "/Users/ashkansamali/jarvis/logs"

# App UI
APP_PORT          = 8000
APP_HOST          = "127.0.0.1"

# WhatsApp (fill in later)
WHATSAPP_ENABLED  = False

# Voice (fill in later)
VOICE_ENABLED     = False
PICOVOICE_KEY = '1y8fhxOCmVhcPu6n73f66vme7Am0dzVAGDoOwZYJBqfmwGcLda/HCA=='

# V5 Additions
GEMINI_API_KEY = 'YOUR_GEMINI_KEY_HERE'
OPENCLAW_URL = 'http://YOUR_REMOTE_IP:8000/generate' # Replace with actual OpenClaw IP

LLAMA_CPP_URL = 'http://localhost:8081/v1/chat/completions'

# Model routing — two tiers
FAST_URL  = 'http://localhost:8080/v1/chat/completions'   # E4B: voice, greetings, quick yes/no
BRAIN_URL = 'http://localhost:8081/v1/chat/completions'   # 31B: CLI, agents, coding, reasoning
