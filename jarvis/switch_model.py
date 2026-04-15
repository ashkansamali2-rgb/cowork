#!/usr/bin/env python3
"""
Easy model switcher for Cowork.
Usage: python3 ~/cowork/jarvis/switch_model.py --port 8081 --model ~/Downloads/new_model.gguf
"""
import argparse, os, re, sys
from pathlib import Path

ZSHRC = Path.home() / ".zshrc"

def list_models():
    models = sorted(Path.home().glob("Downloads/*.gguf"))
    if not models:
        print("No .gguf models found in ~/Downloads/")
        return models
    print("Available models in ~/Downloads:")
    for i, m in enumerate(models):
        size = m.stat().st_size / (1024**3)
        print(f"  {i+1}. {m.name} ({size:.1f}GB)")
    return models

def switch_model(port: int, model_path: str):
    model_path = os.path.expanduser(model_path)
    if not os.path.exists(model_path):
        print(f"Model not found: {model_path}")
        sys.exit(1)

    content = ZSHRC.read_text()

    # Find and replace the model path for this port in llama-server lines
    pattern = rf'(llama-server -m )(.*?)(--port {port})'
    replacement = rf'\g<1>{model_path} \g<3>'
    new_content = re.sub(pattern, replacement, content)

    if new_content == content:
        print(f"Could not find llama-server entry for port {port} in ~/.zshrc")
        sys.exit(1)

    ZSHRC.write_text(new_content)
    print(f"Switched port {port} to: {Path(model_path).name}")
    print(f"Run: source ~/.zshrc && stop && start")

def main():
    parser = argparse.ArgumentParser(description="Switch Cowork models")
    parser.add_argument("--port", type=int, choices=[8080, 8081], help="Port to update")
    parser.add_argument("--model", help="Path to new .gguf model")
    parser.add_argument("--list", action="store_true", help="List available models")
    args = parser.parse_args()

    if args.list or not args.port:
        list_models()
        return

    if not args.model:
        parser.print_help()
        sys.exit(1)

    switch_model(args.port, args.model)

if __name__ == "__main__":
    main()
