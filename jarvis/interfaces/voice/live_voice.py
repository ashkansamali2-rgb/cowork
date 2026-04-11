import asyncio
import os
import sys
import json
import queue
import tempfile
import threading
import random
import re
import time
import subprocess
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

# Fix 1: Replace threading.Lock with asyncio.Lock for gpu_lock
gpu_lock = asyncio.Lock()
tts_lock = threading.Lock()
is_speaking = threading.Event()


def sanitize_for_speech(text):
    text = re.sub(r'```.*?```', ' code snippet removed. ', text, flags=re.DOTALL)
    text = text.replace('`', '').replace('*', '').replace('@', ' at ')
    text = re.sub(r'http\S+', 'a link', text)
    return text.strip()


def truncate_to_sentences(text, n=2):
    """Return first n sentences of text."""
    parts = re.split(r'(?<=[.!?])\s+|\n', text.strip())
    return ' '.join(parts[:n])


def speak_text(text):
    # Truncate to first 2 sentences for faster response
    text = truncate_to_sentences(text, 2)
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
            # Fix 5: Wrap afplay in subprocess with timeout=15
            try:
                subprocess.run(["afplay", tmp], timeout=15)
            except subprocess.TimeoutExpired:
                print("[Voice] TTS playback exceeded 15s — killing and continuing")
                subprocess.run(["pkill", "afplay"], capture_output=True)
            os.remove(tmp)
            is_speaking.clear()
        except Exception as e:
            print(f"[Voice Error] {e} — falling back to Daniel")
            clean = safe_text.replace("'", "").replace('"', "")[:200]
            try:
                subprocess.run(["say", "-v", "Daniel", clean], timeout=15)
            except subprocess.TimeoutExpired:
                subprocess.run(["pkill", "say"], capture_output=True)
            is_speaking.clear()


# ── STT ──────────────────────────────────────────────────────────────────────
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
recognizer = sr.Recognizer()
recognizer.energy_threshold = 150
recognizer.dynamic_energy_threshold = False
recognizer.pause_threshold = 0.6
recognizer.non_speaking_duration = 0.3

WS_URL = "ws://127.0.0.1:8001/ws"
WAKE_WORD = "jarvis"
WATCHDOG_TIMEOUT = 30
RESPONSE_TIMEOUT = 45  # Fix 4: 45s response timeout watchdog
CRASH_LOG = "/tmp/voice_crash.log"

# Fix 2: incoming_audio as asyncio.Queue with maxsize=3
incoming_audio = asyncio.Queue(maxsize=3)


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
        result = mlx_whisper.transcribe(tmp, path_or_hf_repo=WHISPER_MODEL, beam_size=1)
        os.remove(tmp)
        return result["text"].lower().strip()
    except Exception as e:
        print(f"[STT Error] {e}")
        return None


async def listen_and_send():
    # Fix 3: Wrap entire listen_and_send in while True with try/except — never die silently
    while True:
        try:
            print(f"[System] Connecting to Jarvis ({WS_URL})...")
            try:
                ws_conn = await asyncio.wait_for(
                    websockets.connect(WS_URL, ping_interval=None),
                    timeout=10
                )
            except (asyncio.TimeoutError, Exception) as conn_err:
                log_crash(conn_err, context="connection")
                # Fix 6: Play Basso.aiff on connection failure
                subprocess.run(["afplay", "/System/Library/Sounds/Basso.aiff"],
                               capture_output=True, timeout=3)
                print("[System] Connection failed. Retrying in 3 seconds...")
                await asyncio.sleep(3)
                continue

            async with ws_conn as ws:
                print("[System] Link established. JARVIS is online.")
                # Fix 6: Play Tink.aiff on successful connection
                subprocess.run(["afplay", "/System/Library/Sounds/Tink.aiff"],
                               capture_output=True, timeout=3)

                waiting_since_ref = [None]  # shared mutable ref for polling watchdog
                final_received = asyncio.Event()  # Fix 4: event for wait_for timeout
                loop = asyncio.get_running_loop()

                # Receive responses and speak them in background thread
                async def receive_loop():
                    try:
                        async for message in ws:
                            data = json.loads(message)
                            if "msg" in data:
                                print(f"\n[JARVIS] {data['msg'][:120]}")
                            if data.get("type") == "final":
                                waiting_since_ref[0] = None  # reset polling watchdog
                                final_received.set()         # Fix 4: signal wait_for
                                threading.Thread(
                                    target=speak_text,
                                    args=(data["msg"],),
                                    daemon=True
                                ).start()
                    except Exception:
                        pass

                asyncio.create_task(receive_loop())

                # Audio processor: handles queue using async iteration
                async def audio_processor():
                    while True:
                        try:
                            # Fix 2: Use asyncio.Queue.get() — async processing
                            audio = await asyncio.wait_for(incoming_audio.get(), timeout=5)
                        except asyncio.TimeoutError:
                            continue
                        except Exception as e:
                            log_crash(e, context="audio_processor_get")
                            await asyncio.sleep(0.5)
                            continue

                        if audio is None:
                            break

                        # If new audio arrives while speaking: interrupt TTS first
                        if is_speaking.is_set():
                            subprocess.run(["pkill", "afplay"], capture_output=True)
                            is_speaking.clear()
                            await asyncio.sleep(0.1)

                        try:
                            text = await loop.run_in_executor(None, transcribe_audio, audio)
                        except Exception as e:
                            log_crash(e, context="transcribe")
                            continue

                        if not text:
                            continue
                        print(f"\n[You] {text}")
                        if any(w in text for w in ["stop", "cancel", "abort"]):
                            print("[Ears] Kill switch.")
                            try:
                                await ws.send(json.dumps({"message": "SYSTEM_COMMAND_STOP", "source": "voice"}))
                            except Exception:
                                pass
                            waiting_since_ref[0] = None
                            final_received.set()  # unblock any pending wait_for
                            continue
                        if WAKE_WORD in text:
                            command = text.split(WAKE_WORD, 1)[1].strip()
                            subprocess.run(["afplay", "/System/Library/Sounds/Tink.aiff"],
                                           capture_output=True, timeout=3)
                            if command:
                                print(f"[Ears] → Brain: {command}")
                                waiting_since_ref[0] = time.monotonic()
                                # Fix 4: send then await final with 45s timeout via asyncio.wait_for
                                try:
                                    await ws.send(json.dumps({"message": command, "source": "voice"}))
                                except Exception as e:
                                    log_crash(e, context="ws_send")
                                    continue
                                final_received.clear()
                                try:
                                    await asyncio.wait_for(final_received.wait(), timeout=RESPONSE_TIMEOUT)
                                except asyncio.TimeoutError:
                                    _tmsg = "[Watchdog] No 'final' response within 45s — resetting state."
                                    print(_tmsg)
                                    print("...")
                                    try:
                                        with open(CRASH_LOG, "a") as _f:
                                            _f.write(f"[{datetime.now().isoformat()}] {_tmsg}\n")
                                    except Exception:
                                        pass
                                    waiting_since_ref[0] = None
                                    # Don't disconnect on timeout
                            else:
                                print("[Ears] Wake word heard, no command.")

                asyncio.create_task(audio_processor())

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
                            # Fix 1: gpu_lock with asyncio.wait_for timeout=10, never block >3s
                            lock_acquired = False
                            try:
                                await asyncio.wait_for(gpu_lock.acquire(), timeout=10)
                                lock_acquired = True
                            except asyncio.TimeoutError:
                                _warn_msg = "[Warning] gpu_lock timeout — continuing without lock"
                                print(_warn_msg)
                                try:
                                    with open(CRASH_LOG, "a") as _f:
                                        _f.write(f"[{datetime.now().isoformat()}] {_warn_msg}\n")
                                except Exception:
                                    pass

                            def get_audio():
                                try:
                                    return recognizer.listen(source, timeout=None, phrase_time_limit=10)
                                except Exception:
                                    return None

                            try:
                                audio = await loop.run_in_executor(pool, get_audio)
                            finally:
                                if lock_acquired:
                                    gpu_lock.release()

                            if not audio:
                                continue

                            # Fix 2: Queue full — drop oldest, add new
                            if incoming_audio.full():
                                try:
                                    incoming_audio.get_nowait()
                                    print("[Queue] Dropped oldest audio item (queue full)")
                                except asyncio.QueueEmpty:
                                    pass
                            await incoming_audio.put(audio)

        except KeyboardInterrupt:
            raise
        except Exception as e:
            # Fix 3: Log ALL exceptions to crash log, sleep 2, reconnect
            log_crash(e, context="listen_and_send")
            print("[System] Reconnecting in 2 seconds...")
            await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(listen_and_send())
    except KeyboardInterrupt:
        print("\n[Ears] Shutting down.")
        sys.exit(0)
