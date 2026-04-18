#!/usr/bin/env python3
import json
import os
import requests
from pathlib import Path
from core.memory.tripartite_engine import TripartiteEngine

class MemoryEngine:
    def __init__(self, user_model):
        self.user_model = user_model
        # V3 Tripartite Engine handles Episodic + Summary + Semantic facts
        self.engine = TripartiteEngine(user_model)
        self.last_extracted_keys = []

    def forget_last(self) -> str:
        if not self.last_extracted_keys:
            return "No recently extracted facts to forget."
        forgotten = []
        for cat, key in self.last_extracted_keys:
            if self.user_model.forget(key):
                forgotten.append(f"{cat}: {key}")
        self.last_extracted_keys = []
        return f"Forgot: {', '.join(forgotten)}" if forgotten else "Could not find last fact to forget."

    def store_episode(self, user_turn: str, jarvis_response: str):
        """Pass through to Tripartite Engine's episodic/summary flow."""
        self.engine.add_episode(user_turn, jarvis_response)

    def extract_and_store(self, user_turn: str, jarvis_response: str):
        """Pass through to Tripartite Engine's extraction flow."""
        # This will auto-update user_model via tripartite_engine.py logic
        self.engine.extract_and_store(user_turn, jarvis_response)
        # Store for forget-last functionality
        # (Note: tripartite_engine handles the raw model update)
        pass

