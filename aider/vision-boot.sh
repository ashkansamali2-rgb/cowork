#!/bin/bash

# Clear the terminal to make it look like a standalone app
clear

# Force all Aider UI text and your typing to be pure white
export AIDER_MESSAGE_COLOR="white"
export AIDER_USER_INPUT_COLOR="white"
export AIDER_ASSISTANT_OUTPUT_COLOR="white"
export AIDER_SUCCESS_COLOR="white"
export AIDER_COMMIT_COLOR="white"

# Define Vibrant Neon Purple and Bright White
V_PURP="\033[38;5;135m"
WHITE="\033[97m"
RESET="\033[0m"

# Purple top divider
echo -e "${V_PURP}────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────${RESET}"
echo -e "${V_PURP}[CANTIVIA LABS] Mounting Unified Memory & Booting Models...${RESET}"

source /Users/ashkansamali/aider/router_env/bin/activate

# Centered Neon Purple ASCII Art
echo -e "${V_PURP}"
cat << 'ART'
                ██████╗  █████╗ ███╗   ██╗████████╗██╗██╗   ██╗██╗ █████╗     ██╗      █████╗ ██████╗ ███████╗
               ██╔════╝ ██╔══██╗████╗  ██║╚══██╔══╝██║██║   ██║██║██╔══██╗    ██║     ██╔══██╗██╔══██╗██╔════╝
               ██║      ███████║██╔██╗ ██║   ██║   ██║██║   ██║██║███████║    ██║     ███████║██████╔╝███████╗
               ██║      ██╔══██║██║╚██╗██║   ██║   ██║╚██╗ ██╔╝██║██╔══██║    ██║     ██╔══██║██╔══██╗╚════██║
               ╚██████╗ ██║  ██║██║ ╚████║   ██║   ██║ ╚████╔╝ ██║██║  ██║    ███████╗██║  ██║██████╔╝███████║
                ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═══╝  ╚═╝╚═╝  ╚═╝    ╚══════╝╚═╝  ╚═╝╚═════╝ ╚══════╝
ART
echo -e "${RESET}"

# Centered Info Box with White Text and Neon Purple Borders
echo -e "${V_PURP}                                     ╔═════════════════════ ${WHITE}#visionary${V_PURP} ═════════════════════╗${RESET}"
echo -e "${V_PURP}                                     ║                                                      ║${RESET}"
echo -e "${V_PURP}                                     ║       ${WHITE}SYSTEM         Cantivia Labs Local v1.1${V_PURP}        ║${RESET}"
echo -e "${V_PURP}                                     ║       ${WHITE}ENGINE         Gemma 4 e4b // Qwen 3.5 9b${V_PURP}      ║${RESET}"
echo -e "${V_PURP}                                     ║       ${WHITE}LOCALITY       Dublin, IE // Apr 2026${V_PURP}          ║${RESET}"
echo -e "${V_PURP}                                     ║       ${WHITE}WORKSPACE      /Users/ashkansamali${V_PURP}             ║${RESET}"
echo -e "${V_PURP}                                     ║                                                      ║${RESET}"
echo -e "${V_PURP}                                     ╚══════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "${WHITE}                                        Unified Memory Locked // Local Intelligence Active${RESET}"

# Purple bottom divider for the boot sequence
echo -e "${V_PURP}────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────${RESET}"

# Launch the Framework
aider --architect --model openai/planner --editor-model openai/coder --editor-edit-format udiff --no-show-model-warnings

# Purple shutdown sequence
echo -e "${V_PURP}────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────${RESET}"
echo -e "${V_PURP}[CANTIVIA LABS] Flushing Memory & Terminating Neural Nets...${RESET}"
echo -e "${V_PURP}────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────${RESET}"
