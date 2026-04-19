#!/usr/bin/env bash
# Jarvis Deep Architect - Autonomous Swarm Chunker

clear

# Colors
PURPLE='\033[1;35m'
WHITE='\033[0;97m'
DIM='\033[2;37m'
RESET='\033[0m'

printf "${PURPLE}╔════════════════════════════════════════════════════════════╗${RESET}\n"
printf "${PURPLE}║${RESET}  ${WHITE}SYSTEM:${RESET}     Jarvis Deep Architect (Autonomous Loop)        ${PURPLE}║${RESET}\n"
printf "${PURPLE}╚════════════════════════════════════════════════════════════╝${RESET}\n\n"

printf "${WHITE}Please enter your massive project architecture requirements:${RESET}\n> "
read -r USER_PROMPT

if [ -z "$USER_PROMPT" ]; then
    printf "${PURPLE}No input provided. Aborting.${RESET}\n"
    exit 1
fi

export AIDER_CODE_THEME="native"

printf "\n${PURPLE}==> [Phase 1] Generating Master Implementation Plan...${RESET}\n"
/Users/ashkansamali/cowork/venv/bin/aider \
  --model openai/jarvis \
  --openai-api-base http://localhost:8081/v1 \
  --openai-api-key local \
  --no-auto-commits \
  --no-show-model-warnings \
  --message "Act as the Master Software Architect. Prompt: '$USER_PROMPT'. Generate a markdown file named 'IMPLEMENTATION_PLAN.md'. Break the massive project down into exactly 6 distinct, sequential tasks. Every task must start with [TODO]. Save the file."

printf "\n${PURPLE}==> [Phase 2] Spawning Sub-Agent Execution Loop...${RESET}\n"
for i in {1..6}; do
    printf "\n${WHITE}>> Sub-Agent Spawning: Processing Architecture Chunk $i / 6 ...${RESET}\n"
    
    # Run silently and redirect output to a temp log to avoid blowing up the terminal
    /Users/ashkansamali/cowork/venv/bin/aider \
      --model openai/jarvis \
      --openai-api-base http://localhost:8081/v1 \
      --openai-api-key local \
      --no-auto-commits \
      --no-show-model-warnings \
      --message "Read IMPLEMENTATION_PLAN.md. Find the absolute next sequential task marked [TODO]. Change its status to [IN PROGRESS]. Write ALL the beautiful, production-ready code needed to fully complete that exact task, making sure files are created and edited. Then change its status in the plan to [DONE]. If all tasks are already [DONE], just reply exactly with 'ALL_DONE'." > /tmp/jarvis_deep_chunk_$i.log 2>&1
    
    if grep -q "ALL_DONE" /tmp/jarvis_deep_chunk_$i.log; then
        printf "${PURPLE}>> Sub-Agents reported all tasks complete! Exiting loop early.${RESET}\n"
        break
    fi
done

printf "\n${PURPLE}==> SYSTEM OFFLINE. Deep Architecture Compilation Complete!${RESET}\n"
printf "${DIM}(Check IMPLEMENTATION_PLAN.md to see the sub-agent task history)${RESET}\n"
