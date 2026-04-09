#!/bin/bash
source ~/cowork/venv/bin/activate
aider \
  --model openai/gemma \
  --openai-api-base http://localhost:8080/v1 \
  --openai-api-key dummy \
  --yes \
  --no-auto-commits \
  --file ~/cowork/cantivia-bus.py \
  --message "add a docstring to the top of this file explaining what the bus does"
