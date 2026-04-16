#!/usr/bin/env python3
import json
import os
from datetime import datetime
from pathlib import Path

from core.memory.user_model import UserModel

ONBOARDING_STATE_PATH = Path(os.path.expanduser("~/cowork/jarvis/memory/onboarding_state.json"))

QUESTIONS = [
    # Round 1: Identity & work
    ("identity", "name", "First things first—what should I call you?"),
    ("identity", "occupation", "What is your primary occupation or role?"),
    ("identity", "location", "Where are you based or what timezone are you in?"),
    ("identity", "company", "Are you part of a specific company or organization?"),
    ("identity", "work_style", "How would you describe your general work style?"),
    ("goals", "current_focus", "What is your main focus or top priority right now?"),
    ("identity", "role_details", "Could you elaborate a bit on what your day-to-day role involves?"),
    ("relationships", "manager", "Do you report to anyone directly, or are you the boss?"),
    ("relationships", "colleagues", "Who are the main people you collaborate with?"),
    ("raw_facts", "origin", "Where are you originally from?"),

    # Round 2: Tech stack & tools
    ("preferences", "languages", "Moving to tech—what programming languages do you use most often?"),
    ("preferences", "ides", "What are your preferred IDEs or text editors?"),
    ("preferences", "deployment", "How do you usually handle deployment and hosting?"),
    ("preferences", "hardware", "What hardware ecosystem are you using (Mac, PC, Linux)?"),
    ("preferences", "database", "Do you have a preferred database technology?"),
    ("preferences", "frameworks", "Which frontend or backend frameworks do you favor?"),
    ("preferences", "version_control", "What does your version control workflow look like?"),
    ("preferences", "ci_cd", "Do you use any CI/CD tools?"),
    ("preferences", "terminal", "Are you a heavy command-line user? Which shell/terminal?"),
    ("raw_facts", "tech_pet_peeves", "What's your biggest pet peeve when it comes to tools and tech?"),

    # Round 3: Projects & goals
    ("projects", "primary", "What is the primary project you are currently building or maintaining?"),
    ("goals", "timelines", "Are there any strict deadlines or timelines for this project?"),
    ("projects", "blockers", "What are the biggest technical blockers you're facing right now?"),
    ("goals", "short_term", "What is your most important short-term goal for the next week?"),
    ("goals", "long_term", "What is a major long-term goal you're working towards?"),
    ("projects", "past_wins", "What's a past project you're particularly proud of?"),
    ("projects", "side_hustles", "Do you have any side projects currently active?"),
    ("goals", "learning", "Is there a new technology or skill you are trying to learn?"),
    ("raw_facts", "project_metrics", "How do you measure success for your projects?"),
    ("raw_facts", "project_audiences", "Who is the primary audience for the things you build?"),

    # Round 4: Preferences & style
    ("preferences", "communication_style", "How do you prefer I communicate with you? Short and direct, or detailed and explanatory?"),
    ("preferences", "feedback", "How do you like to receive feedback on your code or ideas?"),
    ("preferences", "formality", "Do you prefer a formal tone, or something more casual and relaxed?"),
    ("preferences", "aesthetics", "When it comes to UI/UX, do you lean towards minimalist, complex, vibrant, or dark mode aesthetics?"),
    ("habits", "help_preference", "When you get stuck, do you want me to give you the answer immediately, or guide you to figure it out?"),
    ("preferences", "formatting", "How do you feel about code formatting—any strict rules I should know about?"),
    ("preferences", "verbosity", "Should I provide code snippets only, or include the full file context when answering?"),
    ("preferences", "updates", "Do you want proactive updates when I finish background tasks?"),
    ("raw_facts", "pet_peeves_comm", "Are there any phrases or AI mannerisms you absolutely hate?"),
    ("raw_facts", "praise", "Do you appreciate encouragement, or should we keep it strictly business?"),

    # Round 5: Daily patterns
    ("habits", "daily_routines", "Almost done! When are you usually most productive during the day?"),
    ("habits", "start_session", "How do you typically start a working session?"),
    ("habits", "breaks", "Do you take breaks regularly, or power through?"),
    ("habits", "end_session", "How do you usually wrap up your day?"),
    ("habits", "frustrations", "What usually breaks your flow or frustrates you the most while working?"),
    ("habits", "music", "Do you listen to music while you work? If so, what kind?"),
    ("habits", "meetings", "Are your days heavy with meetings, or mostly uninterrupted coding time?"),
    ("habits", "planning", "Do you plan your tasks meticulously, or prefer spontaneous execution?"),
    ("habits", "documentation", "How do you feel about writing documentation?"),
    ("raw_facts", "closing_thought", "Finally, what's one random thing about you that I should know to be a better assistant?"),
]

class OnboardingTracker:
    def __init__(self, user_model: UserModel):
        self.user_model = user_model
        if ONBOARDING_STATE_PATH.exists():
            self.state = json.loads(ONBOARDING_STATE_PATH.read_text())
        else:
            self.state = {
                "active": False,
                "current_index": 0,
                "completed": False
            }

    def _save(self):
        ONBOARDING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        ONBOARDING_STATE_PATH.write_text(json.dumps(self.state, indent=2))

    def start(self):
        self.state["active"] = True
        self.state["current_index"] = 0
        self.state["completed"] = False
        self._save()
        return "Sir, I noticed I don't know much about you. Could we do a quick onboarding interview? Just 50 questions to help me serve you perfectly. " + QUESTIONS[0][2]

    def is_active(self):
        return self.state.get("active", False)

    def handle_answer(self, answer: str):
        idx = self.state["current_index"]
        if idx >= len(QUESTIONS):
            return self.finish()

        category, key, _ = QUESTIONS[idx]
        
        # Save the structured answer loosely (a real system would synthesize, but we map it directly contextually)
        self.user_model.update(category, key, answer)

        idx += 1
        self.state["current_index"] = idx
        self._save()

        if idx >= len(QUESTIONS):
            return self.finish()
        else:
            # Confirm understanding with varied short positive prefixes
            prefixes = ["Got it.", "Makes sense.", "Understood.", "Noted.", "Interesting."]
            return f"{prefixes[idx % len(prefixes)]} {QUESTIONS[idx][2]}"

    def finish(self):
        self.state["active"] = False
        self.state["completed"] = True
        self._save()
        
        self.user_model.data["onboarding_complete"] = True
        self.user_model.data["onboarding_timestamp"] = datetime.now().isoformat()
        self.user_model.save()
        
        summary = self.user_model.get_profile_summary()
        return f"Thank you! Here is the profile I have constructed for you:\n\n{summary}\n\nDoes this look right? You can always type `/memory edit` or 'remember that...' to change it later."
