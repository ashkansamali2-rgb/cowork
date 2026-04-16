#!/usr/bin/env python3
import json
import os
from pathlib import Path
from datetime import datetime

USER_MODEL_PATH = Path(os.path.expanduser("~/cowork/jarvis/memory/user_model.json"))

class UserModel:
    def __init__(self):
        self.path = USER_MODEL_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self.load()

    def load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:
                pass
        
        return {
            "identity": {"name": "", "age": "", "location": "", "occupation": "", "work_style": ""},
            "preferences": {"languages": [], "tools": [], "aesthetics": "", "communication_style": ""},
            "projects": {},
            "habits": {"daily_routines": [], "work_patterns": [], "common_requests": {}},
            "goals": {"short_term": [], "long_term": [], "current_focus": ""},
            "relationships": {},
            "raw_facts": {},
            "onboarding_complete": False,
            "onboarding_timestamp": None
        }

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2))

    def update(self, category: str, key: str, value: str):
        self.data = self.load()
        if category in self.data:
            if isinstance(self.data[category], dict):
                self.data[category][key] = value
            elif isinstance(self.data[category], list) and value not in self.data[category]:
                self.data[category].append(value)
        else:
            self.data["raw_facts"][key] = value
        self.save()

    def forget(self, key: str) -> bool:
        self.data = self.load()
        found = False
        for cat in self.data:
            if isinstance(self.data[cat], dict) and key in self.data[cat]:
                del self.data[cat][key]
                found = True
        self.save()
        return found

    def get_profile_summary(self) -> str:
        d = self.data
        lines = ["[USER PROFILE]"]
        
        name = d["identity"].get("name")
        occup = d["identity"].get("occupation")
        if name or occup:
            lines.append(f"- Identity: {name or 'User'}, {occup or 'Professional'}")
            
        prefs = d.get("preferences", {})
        if prefs.get("communication_style"):
            lines.append(f"- Communication Style: {prefs['communication_style']}")
            
        lines.append(f"- Active Projects: {', '.join(d['projects'].keys()) if d['projects'] else 'None known'}")
        lines.append(f"- Current Focus: {d['goals'].get('current_focus', 'Unknown')}")
        
        facts = [f"{k}: {v}" for k, v in d.get("raw_facts", {}).items()][:5]
        if facts:
            lines.append("- Recent Facts: " + " | ".join(facts))
            
        return "\n".join(lines)

    def get_relevant_context(self, query: str) -> str:
        # A simple matching extraction of relevant facts
        ql = query.lower()
        relevant = []
        for cat, content in self.data.items():
            if isinstance(content, dict):
                for k, v in content.items():
                    if ql in str(k).lower() or ql in str(v).lower():
                        relevant.append(f"{cat}.{k}: {v}")
        return "\n".join(relevant) if relevant else ""

    def is_empty(self) -> bool:
        return not self.data.get("identity", {}).get("name") and not self.data.get("onboarding_complete")
