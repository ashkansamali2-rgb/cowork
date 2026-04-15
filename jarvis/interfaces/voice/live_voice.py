#!/usr/bin/env python3
import asyncio
import os
import sys
import json
import tempfile
import threading
import random
import re
import time
import subprocess
import traceback
from datetime import datetime

import numpy as np
import soundfile as sf
import speech_recognition as sr
import mlx_whisper
import websockets

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
import warnings
warnings.filterwarnings("ignore")

from mlx_audio.tts.utils import load_model
print("[System] Booting Qwen3-TTS...")
tts_model = load_model("mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16")

JARVIS_AUDIO_PATH = os.path.expanduser("~/cowork/jarvis/jarvis.wav")
JARVIS_AUDIO_TEXT = "Sir, I've detected an anomaly in the primary power grid. Current efficiency is at 78.3%, suggesting a potential optimization requirement. Shall I begin diagnostic protocols and prepare contingency measures for your review?"

GREETINGS = [
    "Systems are fully online, sir. How can I assist you?",
    "Good to see you, sir. Awaiting your command.",
]

# We use a simple event flag to tell the mic loop to drop frames while speaking
is_speaking = threading.Event()

WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo-q4"
JARVIS_WS = "ws://127.0.0.1:8001/ws"
WAKE_WORD = "jarvis"

recognizer = sr.Recognizer()
recognizer.energy_threshold = 300
recognizer.dynamic_energy_threshold = False
recognizer.pause_threshold = 0.6
recognizer.non_speaking_duration = 0.3

def sanitize_for_speech(text):
    text = re.sub(r'```.*?```', ' code snippet removed. ', text, flags=re.DOTALL)
    text = text.replace('`', '').replace('*', '').replace('@', ' at ')
    text = re.sub(r'http\S+', 'a link', text)
    return text.strip()

def truncate_to_sentences(text, n=2):
    parts = re.split(r'(?<=[.!?])\s+|\n', text.strip())
    return ' '.join(parts[:n])

def speak_text(text):
    text = truncate_to_sentences(text, 2)
    safe_text = sanitize_for_speech(text)
    print(f"[Voice] Speaking: {safe_text[:80]}")
    try:
        results = list(tts_model.generate(
            text=safe_text,
            ref_audio=JARVIS_AUDIO_PATH,
            ref_text=JARVIS_AUDIO_TEXT,
            language="English"
        ))
        audio = np.clip(np.array(results[0].audio) * 1.8, -1.0, 1.0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
        sf.write(tmp, audio, 24000)
        
        try:
            subprocess.run(["afplay", tmp], timeout=15)
        except subprocess.TimeoutExpired:
            subprocess.run(["pkill", "afplay"], capture_output=True)
        os.remove(tmp)
    except Exception as e:
        print(f"[Voice Error] {e} — falling back to OSX say")
        clean = safe_text.replace("'", "").replace('"', "")[:200]
        subprocess.run(["say", "-v", "Daniel", clean])

# ── Coroutine 1: mic_loop ───────────────────────────────────────────────
async def mic_loop(cmd_q: asyncio.Queue):
    """Continuously reads mic. Skips detection/transcription when speaking."""
    loop = asyncio.get_running_loop()
    with sr.Microphone() as source:
        print("[Mic] Calibrating...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print("[Mic] Ready. Say 'Jarvis' to wake.")
        
        while True:
            # Drain the buffer if currently speaking to prevent buildup & echoes
            if is_speaking.is_set():
                try: recognizer.listen(source, timeout=0.1)
                except Exception: pass
                await asyncio.sleep(0.1)
                continue

            def get_audio():
                try: return recognizer.listen(source, timeout=1.0, phrase_time_limit=10)
                except Exception: return None
            
            audio = await loop.run_in_executor(None, get_audio)
            if not audio: continue

            # Immediately check speaking flag again before heavy transcribe
            if is_speaking.is_set(): continue

            def transcribe():
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio.get_wav_data())
                    tmp = f.name
                res = mlx_whisper.transcribe(tmp, path_or_hf_repo=WHISPER_MODEL, beam_size=1)
                os.remove(tmp)
                return res.get("text", "").lower().strip()

            text = await loop.run_in_executor(None, transcribe)
            if not text: continue
            print(f"\n[You] {text}")

            if "stop" in text or "cancel" in text:
                await cmd_q.put("stop")
                continue

            if WAKE_WORD in text:
                cmd = text.split(WAKE_WORD, 1)[1].strip()
                if cmd:
                    print(f"[Ears] Command: {cmd}")
                    subprocess.run(["afplay", "/System/Library/Sounds/Tink.aiff"], timeout=2)
                    await cmd_q.put(cmd)

# ── Coroutine 2: ws_loop ────────────────────────────────────────────────
async def ws_loop(cmd_q: asyncio.Queue, tts_q: asyncio.Queue):
    """Handles communication with the external Jarvis system."""
    while True:
        try:
            async with websockets.connect(JARVIS_WS, ping_interval=None) as ws:
                print("[System] WS Connected to Brain.")
                # Greet on first connect
                await tts_q.put(random.choice(GREETINGS))

                async def send():
                    while True:
                        cmd = await cmd_q.get()
                        if cmd == "stop":
                            await ws.send(json.dumps({"message": "SYSTEM_COMMAND_STOP", "source": "voice"}))
                        else:
                            await ws.send(json.dumps({"message": cmd, "source": "voice"}))
                
                async def recv():
                    async for msg in ws:
                        data = json.loads(msg)
                        if data.get("type") == "final":
                            # Drop ongoing TTS immediately if new final comes in
                            if is_speaking.is_set():
                                subprocess.run(["pkill", "afplay"], capture_output=True)
                            await tts_q.put(data["msg"])
                            
                await asyncio.gather(send(), recv())
        except Exception as e:
            print(f"[WS Error] {e} - reconnecting in 3s...")
            await asyncio.sleep(3)

# ── Coroutine 3: tts_loop ────────────────────────────────────────+++++++
async def tts_loop(tts_q: asyncio.Queue):
    """Drains the TTS queue sequentially."""
    loop = asyncio.get_running_loop()
    while True:
        text = await tts_q.get()
        # Set the global flag so mic skips frames
        is_speaking.set()
        try:
            await loop.run_in_executor(None, speak_text, text)
        finally:
            # Always ensure mic gets cleared at the end
            is_speaking.clear()

async def main():
    cmd_q = asyncio.Queue()
    tts_q = asyncio.Queue()

    await asyncio.gather(
        mic_loop(cmd_q),
        ws_loop(cmd_q, tts_q),
        tts_loop(tts_q)
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown.")
        sys.exit(0)
