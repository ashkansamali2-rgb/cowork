#!/usr/bin/env python3
import asyncio
import os
import sys
import json
import tempfile
import random
import re
import time
import subprocess
import traceback
from datetime import datetime
import threading

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

WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo-q4"
JARVIS_WS = "ws://127.0.0.1:8001/ws"
WAKE_WORD = "jarvis"

recognizer = sr.Recognizer()
recognizer.energy_threshold = 300
recognizer.dynamic_energy_threshold = False
recognizer.pause_threshold = 0.6
recognizer.non_speaking_duration = 0.3

gpu_lock = threading.Lock()

def sanitize_for_speech(text):
    text = re.sub(r'```.*?```', ' code snippet removed. ', text, flags=re.DOTALL)
    text = text.replace('`', '').replace('*', '').replace('@', ' at ')
    text = re.sub(r'http\S+', 'a link', text)
    return text.strip()

def truncate_to_sentences(text, n=2):
    parts = re.split(r'(?<=[.!?])\s+|\n', text.strip())
    return ' '.join(parts[:n])

async def speak_text(text):
    text = truncate_to_sentences(text, 2)
    safe_text = sanitize_for_speech(text)
    print(f"[Voice] Speaking: {safe_text[:80]}")
    try:
        def generate_audio():
            with gpu_lock:
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
            return tmp
            
        tmp = await asyncio.to_thread(generate_audio)
        
        try:
            await asyncio.wait_for(asyncio.to_thread(subprocess.run, ["afplay", tmp]), timeout=15)
        except asyncio.TimeoutError:
            await asyncio.to_thread(subprocess.run, ["pkill", "afplay"], capture_output=True)
        os.remove(tmp)
    except Exception as e:
        print(f"[Voice Error] {e} — falling back to OSX say")
        clean = safe_text.replace("'", "").replace('"', "")[:200]
        await asyncio.to_thread(subprocess.run, ["say", "-v", "Daniel", clean])

# ── Coroutine 1: mic_loop ───────────────────────────────────────────────
async def mic_loop(audio_q: asyncio.Queue):
    """Continuously reads mic. Puts frames into an asyncio.Queue, no exceptions."""
    loop = asyncio.get_running_loop()
    with sr.Microphone() as source:
        print("[Mic] Calibrating...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print('◆ Voice active. Listening for "jarvis"...')
        
        while True:
            def get_audio():
                try: return recognizer.listen(source, timeout=1.0, phrase_time_limit=10)
                except Exception: return None
            
            audio = await loop.run_in_executor(None, get_audio)
            if audio:
                await audio_q.put(audio)

# ── Coroutine 2: process_loop ───────────────────────────────────────────
async def process_loop(audio_q: asyncio.Queue, cmd_q: asyncio.Queue):
    """Pulls from the queue, runs Whisper, detects wake word, triggers response."""
    loop = asyncio.get_running_loop()
    while True:
        audio = await audio_q.get()
        if not audio: continue

        def transcribe():
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio.get_wav_data())
                tmp = f.name
            with gpu_lock:
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
                await asyncio.to_thread(subprocess.run, ["afplay", "/System/Library/Sounds/Tink.aiff"])
                await cmd_q.put(cmd)

# ── Coroutine 3: ws_loop ────────────────────────────────────────────────
async def ws_loop(cmd_q: asyncio.Queue, tts_q: asyncio.Queue):
    """Handles communication with the external Jarvis system."""
    while True:
        try:
            async with websockets.connect(JARVIS_WS, ping_interval=None) as ws:
                print("[System] WS Connected to Brain.")
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
                            await asyncio.to_thread(subprocess.run, ["pkill", "afplay"], capture_output=True)
                            await tts_q.put(data["msg"])
                            
                await asyncio.gather(send(), recv())
        except Exception as e:
            print(f"[WS Error] {e} - reconnecting in 3s...")
            await asyncio.sleep(3)

# ── Coroutine 4: tts_loop ────────────────────────────────────────+++++++
async def tts_loop(tts_q: asyncio.Queue):
    """Drains the TTS queue sequentially."""
    while True:
        text = await tts_q.get()
        await speak_text(text)

async def main():
    cmd_q = asyncio.Queue()
    tts_q = asyncio.Queue()
    audio_q = asyncio.Queue()

    await asyncio.gather(
        mic_loop(audio_q),
        process_loop(audio_q, cmd_q),
        ws_loop(cmd_q, tts_q),
        tts_loop(tts_q)
    )

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\nShutdown.")
            sys.exit(0)
        except Exception as e:
            print(f"[System] Voice restarting... ({e})")
            time.sleep(2)
