import sys, os
sys.path.insert(0, os.path.expanduser("~/jarvis"))
from core.memory import remember, recall

def think(user_message: str) -> dict:
    t = user_message.lower()

    # remember this message
    remember(f"User: {user_message}", {"type": "conversation"}, collection="conversations")

    # CAD keywords — wake up 30B
    if any(k in t for k in ["blender", "3d model", "cad", "3d object", "mesh", 
                              "cylinder", "cube", "sphere", "extrude", "sculpt",
                              "render", "3d print", "solidworks", "create a box",
                              "create a shape", "3d scene"]):
        print("[Brain] CAD detected — routing to cad branch")
        return {"branch": "cad", "plan": [], "instruction": user_message}

    # coding keywords
    if any(k in t for k in ["write code", "write a script", "write a function",
                              "write a program", "create a script", "build a",
                              "project vision", "coding", "python script",
                              "javascript", "html", "css", "api", "database",
                              "debug", "fix the bug", "refactor"]):
        print("[Brain] Coding detected — routing to coding branch")
        return {"branch": "coding", "plan": [], "instruction": user_message}

    # everything else goes to general
    print("[Brain] Routing to general branch")
    return {"branch": "general", "plan": [], "instruction": user_message}

if __name__ == "__main__":
    print(think("create a cube in blender"))
    print(think("write a python script"))
    print(think("what time is it"))
    print(think("how are you"))

# OpenClaw routing (appended)
_original_think = think
def think(message: str) -> dict:
    msg = message.lower()
    if any(k in msg for k in ["linux", "other pc", "openclaw", "claw", "remote pc", "tell the pc", "on the pc"]):
        return {"branch": "openclaw", "plan": [], "instruction": message}
    return _original_think(message)
