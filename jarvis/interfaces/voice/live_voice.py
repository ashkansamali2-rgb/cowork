import asyncio
import os
import sys
import json
import tempfile
import threading
import random
import re
import time
import concurrent.futures
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

# ── TTS ──────────────────────────────────────────────────────────────────────
from mlx_audio.tts.utils import load_model
print("[System] Booting Qwen3-TTS...")
tts_model = load_model("mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16")

JARVIS_AUDIO_PATH = os.path.expanduser("~/cowork/jarvis/jarvis.wav")
JARVIS_AUDIO_TEXT = "Sir, I've detected an anomaly in the primary power grid. Current efficiency is at 78.3%, suggesting a potential optimization requirement. Shall I begin diagnostic protocols and prepare contingency measures for your review?"

GREETINGS = [
    "Systems are fully online, sir. How can I assist you?",
    "Good to see you, sir. Awaiting your command.",
    "Boot sequence complete. What is on the agenda for today?",
    "I am online and ready, sir.",
    "Facility secure. Neural network is spooled up. How can I help?"
]

tts_lock = threading.Lock()
is_speaking = threading.Event()

def sanitize_for_speech(text):
    text = re.sub(r'```.*?```', ' code snippet removed. ', text, flags=re.DOTALL)
    text = text.replace('`', '').replace('*', '').replace('@', ' at ')
    text = re.sub(r'http\S+', 'a link', text)
    return text.strip()

def speak_text(text):
    safe_text = sanitize_for_speech(text)
    print(f"[Voice] Speaking: {safe_text[:80]}")
    is_speaking.set()
    with tts_lock:
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
            os.system(f"afplay {tmp}")
            os.remove(tmp)
            is_speaking.clear()
        except Exception as e:
            print(f"[Voice Error] {e} — falling back to Daniel")
            clean = safe_text.replace("'", "").replace('"', "")[:200]
            os.system(f"say -v Daniel '{clean}'")
            is_speaking.clear()

# ── STT ──────────────────────────────────────────────────────────────────────
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
recognizer = sr.Recognizer()
recognizer.energy_threshold = 150
recognizer.dynamic_energy_threshold = False
recognizer.pause_threshold = 1.5
recognizer.non_speaking_duration = 0.5

WS_URL = "ws://127.0.0.1:8001/ws"
WAKE_WORD = "jarvis"
WATCHDOG_TIMEOUT = 30
CRASH_LOG = "/tmp/voice_crash.log"


def log_crash(exc: Exception, context: str = ""):
    timestamp = datetime.now().isoformat()
    label = f" ({context})" if context else ""
    entry = f"[{timestamp}] CRASH{label}: {type(exc).__name__}: {exc}\n"
    try:
        with open(CRASH_LOG, "a") as f:
            f.write(entry)
    except Exception:
        pass
    print(f"[System] {entry.strip()}")

def transcribe_audio(audio) -> str | None:
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio.get_wav_data())
            tmp = f.name
        result = mlx_whisper.transcribe(tmp, path_or_hf_repo=WHISPER_MODEL)
        os.remove(tmp)
        return result["text"].lower().strip()
    except Exception as e:
        print(f"[STT Error] {e}")
        return None

async def listen_and_send():
    while True:
        try:
            print(f"[System] Connecting to Jarvis ({WS_URL})...")
            async with websockets.connect(WS_URL, ping_interval=None) as ws:
                print("[System] Link established. JARVIS is online.")

                waiting_since = None  # set when a command is sent; cleared on "final"

                # Receive responses and speak them in background thread
                async def receive_loop():
                    nonlocal waiting_since
                    try:
                        async for message in ws:
                            data = json.loads(message)
                            if "msg" in data:
                                print(f"\n[JARVIS] {data['msg'][:120]}")
                            if data.get("type") == "final":
                                waiting_since = None  # reset watchdog
                                threading.Thread(
                                    target=speak_text,
                                    args=(data["msg"],),
                                    daemon=True
                                ).start()
                    except Exception:
                        pass

                asyncio.create_task(receive_loop())

                loop = asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    with sr.Microphone() as source:
                        print("[Mic] Calibrating...")
                        recognizer.adjust_for_ambient_noise(source, duration=1)
                        print("[Mic] Ready. Say 'Jarvis' to wake.")
                        threading.Thread(
                            target=speak_text,
                            args=(random.choice(GREETINGS),),
                            daemon=True
                        ).start()

                        while True:
                            # Drain mic buffer while Jarvis is speaking
                            if is_speaking.is_set():
                                try:
                                    while is_speaking.is_set():
                                        source.stream.read(source.CHUNK)
                                except Exception:
                                    pass
                                continue

                            # Watchdog: if no "final" received within 30s, reconnect
                            if waiting_since is not None and time.monotonic() - waiting_since > WATCHDOG_TIMEOUT:
                                raise RuntimeError("Watchdog: no final response within 30s — reconnecting")

                            def get_audio():
                                try:
                                    return recognizer.listen(source, timeout=None)
                                except Exception:
                                    return None

                            audio = await loop.run_in_executor(pool, get_audio)
                            if not audio:
                                continue

                            # Drain again in case speaking started during listen
                            if is_speaking.is_set():
                                try:
                                    while is_speaking.is_set():
                                        source.stream.read(source.CHUNK)
                                except Exception:
                                    pass
                                continue

                            text = await asyncio.to_thread(transcribe_audio, audio)
                            if not text:
                                continue

                            print(f"\n[You] {text}")

                            if any(w in text for w in ["stop", "cancel", "abort"]):
                                print("[Ears] Kill switch.")
                                await ws.send(json.dumps({"message": "SYSTEM_COMMAND_STOP"}))
                                waiting_since = None
                                continue

                            if WAKE_WORD in text:
                                command = text.split(WAKE_WORD, 1)[1].strip()
                                if command:
                                    print(f"[Ears] → Brain: {command}")
                                    waiting_since = time.monotonic()  # arm watchdog
                                    await ws.send(json.dumps({"message": command}))
                                else:
                                    print("[Ears] Wake word heard, no command.")

        except KeyboardInterrupt:
            raise
        except Exception as e:
            log_crash(e, context="listen_and_send")
            print("[System] Reconnecting in 3 seconds...")
            await asyncio.sleep(3)

if __name__ == "__main__":
    try:
        asyncio.run(listen_and_send())
    except KeyboardInterrupt:
        print("\n[Ears] Shutting down.")
        sys.exit(0)
