import sys, os
sys.path.insert(0, os.path.expanduser('~/jarvis'))
from core.router import run

print("\n" + "="*50)
print("  MISSION CONTROL — Terminal Mode")
print("  Type your task and press Enter.")
print("  Ctrl+C to quit.")
print("="*50 + "\n")

while True:
    try:
        msg = input("You: ").strip()
        if not msg:
            continue
        out = run(msg)
        print(f"\nJarvis [{out['branch']}]:\n{out['result'][:1200]}\n")
    except KeyboardInterrupt:
        print("\nMission Control offline.")
        sys.exit(0)
