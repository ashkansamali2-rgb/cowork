# ============================================================
#  JARVIS CONFIG — edit this file with your settings
# ============================================================
# Active models: E4B (port 8080) fast/voice, 31B (port 8081) coding/agents

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

# Single model — Gemma 4 31B handles everything
LLAMA_CPP_FAST_URL = 'http://127.0.0.1:8081/v1/chat/completions'
LLAMA_CPP_URL = 'http://127.0.0.1:8081/v1/chat/completions'
BRAIN_URL     = LLAMA_CPP_URL
