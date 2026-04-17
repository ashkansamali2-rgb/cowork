#!/usr/bin/env bash
# Jarvis CLI — Shell wrapper launching aider with local LLM

clear

# Colors
PURPLE='\033[1;35m'
DPURPLE='\033[0;35m'
WHITE='\033[0;97m'
DIM='\033[2;37m'
RESET='\033[0m'

# Terminal width
COLS=$(tput cols 2>/dev/null || echo 80)

# ── LOGO (correct JARVIS — the J has the bottom hook) ─────────────────────
LOGO=(
  '     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗'
  '     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝'
  '     ██║███████║██████╔╝██║   ██║██║███████╗'
  '██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║'
  '╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║'
  ' ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝'
)

printf "${PURPLE}"
for line in "${LOGO[@]}"; do
  line_len=${#line}
  pad=$(( (COLS - line_len) / 2 ))
  [ $pad -lt 0 ] && pad=0
  printf "%*s%s\n" $pad "" "$line"
done
printf "${RESET}\n"

# ── INFO BOX (fixed inner width = 60) ─────────────────────────────────────
W=60
DATE="$(date '+%Y-%m-%d')"
CWD="$(pwd)"
BOX_PAD=$(( (COLS - W - 2) / 2 ))
[ $BOX_PAD -lt 0 ] && BOX_PAD=0
SP=$(printf '%*s' $BOX_PAD '')

printf "${SP}${PURPLE}╔$(printf '═%.0s' $(seq 1 $W))╗${RESET}\n"
printf "${SP}${PURPLE}║${RESET}$(printf '%-*s' $W '')${PURPLE}║${RESET}\n"
printf "${SP}${PURPLE}║${RESET}  ${WHITE}SYSTEM:${RESET}     $(printf '%-*s' $((W - 16)) 'Jarvis Local v1.0')${PURPLE}║${RESET}\n"
printf "${SP}${PURPLE}║${RESET}  ${WHITE}ENGINE:${RESET}     $(printf '%-*s' $((W - 16)) 'LLaMA 31B IQ4 (Local)')${PURPLE}║${RESET}\n"
printf "${SP}${PURPLE}║${RESET}  ${WHITE}LOCALITY:${RESET}   $(printf '%-*s' $((W - 16)) "Dublin, IE // ${DATE}")${PURPLE}║${RESET}\n"
printf "${SP}${PURPLE}║${RESET}  ${WHITE}WORKSPACE:${RESET}  $(printf '%-*s' $((W - 16)) "${CWD}")${PURPLE}║${RESET}\n"
printf "${SP}${PURPLE}║${RESET}  ${WHITE}MODE:${RESET}       $(printf '%-*s' $((W - 16)) 'Architect // Local Intelligence')${PURPLE}║${RESET}\n"
printf "${SP}${PURPLE}║${RESET}$(printf '%-*s' $W '')${PURPLE}║${RESET}\n"
printf "${SP}${PURPLE}╚$(printf '═%.0s' $(seq 1 $W))╝${RESET}\n"

# ── DIVIDER ───────────────────────────────────────────────────────────────
printf "${PURPLE}$(printf '─%.0s' $(seq 1 $COLS))${RESET}\n"

# ── STATUS LINE (centered) ───────────────────────────────────────────────
MSG="Unified Memory Locked // Local Intelligence Active"
PAD=$(( (COLS - ${#MSG}) / 2 ))
printf "%*s${WHITE}${MSG}${RESET}\n" $PAD ''

# ── DIVIDER ───────────────────────────────────────────────────────────────
printf "${PURPLE}$(printf '─%.0s' $(seq 1 $COLS))${RESET}\n\n"

# ── QUICK REFERENCE ──────────────────────────────────────────────────────
printf "${DIM}  Commands:  /help  /add <file>  /drop <file>  /ask <question>  /architect${RESET}\n"
printf "${DIM}             /map  /tokens  /undo  /diff  /git <cmd>  /run <cmd>  /quit${RESET}\n"
printf "${DIM}  Memory:    /remember <fact>  — saves to Jarvis long-term memory${RESET}\n"
printf "${DIM}             /recall <topic>   — retrieves from memory${RESET}\n"
printf "${DIM}             /clear-history    — resets conversation context${RESET}\n\n"

# ── ACTIVATE VENV ─────────────────────────────────────────────────────────
if [ -f ~/cowork/jarvis/.venv/bin/activate ]; then
    source ~/cowork/jarvis/.venv/bin/activate
elif [ -f ~/cowork/venv/bin/activate ]; then
    source ~/cowork/venv/bin/activate
fi

# ── AIDER COLORS ──────────────────────────────────────────────────────────
export AIDER_USER_INPUT_COLOR="#7C3AED"
export AIDER_ASSISTANT_OUTPUT_COLOR="#FFFFFF"
export AIDER_TOOL_OUTPUT_COLOR="#9F67F5"
export AIDER_CODE_THEME="monokai"

# ── LAUNCH AIDER IN PROJECT DIR ──────────────────────────────────────────
cd ~/cowork && /Users/ashkansamali/cowork/venv/bin/aider \
  --architect \
  --model openai/jarvis \
  --editor-model openai/jarvis \
  --openai-api-base http://localhost:8081/v1 \
  --openai-api-key local \
  --no-show-model-warnings \
  --no-auto-commits \
  --map-tokens 2048 \
  --edit-format udiff

# ── EXIT ──────────────────────────────────────────────────────────────────
printf "\n${PURPLE}$(printf '─%.0s' $(seq 1 $COLS))${RESET}\n"
printf "${DIM}Jarvis offline. Session ended.${RESET}\n"
