import subprocess, sys, os
sys.path.insert(0, os.path.expanduser("~/jarvis"))

LINUX_HOST = "bot@192.168.0.193"
SSH_KEY = os.path.expanduser("~/.ssh/openclaw_key")

def send_to_openclaw(message: str) -> str:
    try:
        cmd = [
            "ssh", "-i", SSH_KEY,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            LINUX_HOST,
            f"/home/bot/.npm-global/bin/openclaw agent --agent main --message '{message}' 2>&1"
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = r.stdout.strip() or r.stderr.strip()
        return output or "Command sent to Linux PC"
    except Exception as e:
        return f"SSH Error: {e}"

def handle(instruction: str, context: dict = {}) -> str:
    return send_to_openclaw(instruction)

if __name__ == "__main__":
    print(send_to_openclaw("what can you do?"))
