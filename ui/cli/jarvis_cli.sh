#!/usr/bin/env bash
# Jarvis CLI — Shell wrapper launching aider with local LLM

clear

# Colors
PURPLE='\033[1;35m'
WHITE='\033[0;97m'
DIM='\033[2;37m'
RESET='\033[0m'

# ── LOGO ─────────────────────────────────────────────────────────────────
printf "${PURPLE}"
printf '██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗\n'
printf '██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝\n'
printf '██║███████║██████╔╝██║   ██║██║███████╗\n'
printf '██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║\n'
printf '██║██║  ██║██║  ██║ ╚████╔╝ ██║███████║\n'
printf '╚═╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝\n'
printf "${RESET}\n"

# ── INFO BOX ──────────────────────────────────────────────────────────────
DATE="$(date '+%Y-%m-%d')"
CWD="$(pwd)"
WIDTH=52

printf "${PURPLE}╔$(printf '═%.0s' $(seq 1 $WIDTH))╗${RESET}\n"
printf "${PURPLE}║${RESET}  %-${WIDTH}s${PURPLE}║${RESET}\n" ""
printf "${PURPLE}║${RESET}  ${WHITE}SYSTEM:${RESET}     Jarvis Local v1.0$(printf ' %.0s' $(seq 1 $((WIDTH - 30))))${PURPLE}║${RESET}\n"
printf "${PURPLE}║${RESET}  ${WHITE}ENGINE:${RESET}     Gemma 4 E4B // Gemma 4 31B$(printf ' %.0s' $(seq 1 $((WIDTH - 36))))${PURPLE}║${RESET}\n"
printf "${PURPLE}║${RESET}  ${WHITE}LOCALITY:${RESET}   Dublin, IE // ${DATE}$(printf ' %.0s' $(seq 1 $((WIDTH - 30 - ${#DATE}))))${PURPLE}║${RESET}\n"
printf "${PURPLE}║${RESET}  ${WHITE}WORKSPACE:${RESET}  ${CWD}$(printf ' %.0s' $(seq 1 $((WIDTH - 12 - ${#CWD}))))${PURPLE}║${RESET}\n"
printf "${PURPLE}║${RESET}  %-${WIDTH}s${PURPLE}║${RESET}\n" ""
printf "${PURPLE}╚$(printf '═%.0s' $(seq 1 $WIDTH))╝${RESET}\n"

# ── DIVIDER ───────────────────────────────────────────────────────────────
printf "${PURPLE}$(printf '─%.0s' $(seq 1 54))${RESET}\n"

# ── STATUS LINE ───────────────────────────────────────────────────────────
MSG="Unified Memory Locked // Local Intelligence Active"
PAD=$(( (54 - ${#MSG}) / 2 ))
printf "${WHITE}$(printf ' %.0s' $(seq 1 $PAD))${MSG}${RESET}\n"

# ── DIVIDER ───────────────────────────────────────────────────────────────
printf "${PURPLE}$(printf '─%.0s' $(seq 1 54))${RESET}\n\n"

# ── ACTIVATE VENV ─────────────────────────────────────────────────────────
if [ -f ~/cowork/jarvis/.venv/bin/activate ]; then
    source ~/cowork/jarvis/.venv/bin/activate
elif [ -f ~/cowork/venv/bin/activate ]; then
    source ~/cowork/venv/bin/activate
fi

# ── LAUNCH AIDER ─────────────────────────────────────────────────────────
aider \
  --architect \
  --model openai/planner \
  --editor-model openai/coder \
  --editor-edit-format udiff \
  --no-show-model-warnings \
  --openai-api-base http://localhost:8081/v1 \
  --openai-api-key local

# ── EXIT ──────────────────────────────────────────────────────────────────
printf "\n${PURPLE}$(printf '─%.0s' $(seq 1 54))${RESET}\n"
printf "${DIM}Jarvis offline. Session ended.${RESET}\n"
