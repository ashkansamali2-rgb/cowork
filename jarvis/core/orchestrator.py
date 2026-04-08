import requests, sys, os, re
sys.path.insert(0, os.path.expanduser("~/jarvis"))
from core.search import search, search_and_browse

LLAMA_URL = "http://localhost:11435"
CONVERSATIONAL = ["how are you", "who are you", "hello", "hi ", "thanks", "thank you", "bye"]

def call_brain(prompt: str) -> str:
    try:
        r = requests.post(
            f"{LLAMA_URL}/v1/chat/completions",
            json={
                "model": "jarvis",
                "messages": [
                    {"role": "system", "content": "/no_think You are Jarvis, a concise AI assistant. Reply in 1-2 sentences only. No explanations. No thinking."},
                    {"role": "user", "content": "/no_think " + prompt}
                ],
                "max_tokens": 150,
                "temperature": 0.1,
                "thinking": False
            },
            timeout=120
        )
        data = r.json()
        msg = data["choices"][0]["message"]
        # try content first
        text = msg.get("content", "").strip()
        # fallback to reasoning_content and extract last meaningful line
        if not text:
            rc = msg.get("reasoning_content", "")
            lines = [l.strip() for l in rc.split("\n") if l.strip() and not l.strip().startswith(("*", "#", "1.", "2.", "3.", "-"))]
            text = lines[-1] if lines else "Done."
        # strip any remaining think tags
        if "<think>" in text:
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return text[:200] or "Done."
    except Exception as e:
        return f"Error: {e}"

def clean(text: str) -> str:
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    seen = []
    for s in sentences:
        s = s.strip()
        if not s or s in seen:
            break
        seen.append(s)
    return " ".join(seen[:3])

def execute(instruction: str, branch: str = "general") -> str:
    msg_lower = instruction.lower()
    is_convo = any(k in msg_lower for k in CONVERSATIONAL)
    search_context = ""

    if not is_convo:
        if branch == "cad":
            search_context = search(f"Blender Python bpy {instruction}")
        elif branch == "coding":
            search_context = search(instruction)
        elif branch == "general":
            if any(k in msg_lower for k in ["what", "who", "where", "when", "how", "search", "find", "look up", "latest", "news"]):
                print("[Orchestrator] Searching...")
                search_context = search(instruction)
                print(f"[Orchestrator] Got {len(search_context)} chars")

    if search_context and len(search_context) > 20:
        prompt = f"Answer in 1-2 sentences using this info: {search_context[:500]}\n\nQuestion: {instruction}"
    elif is_convo:
        prompt = instruction
    else:
        prompt = instruction

    return call_brain(prompt)

if __name__ == "__main__":
    print(execute("hello", "general"))
    print(execute("what is 2+2", "general"))
