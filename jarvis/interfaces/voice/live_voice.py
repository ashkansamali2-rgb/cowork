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
import traceback
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

# asyncio.Lock for GPU (whisper) — acquired with 10s timeout
gpu_lock = asyncio.Lock()
tts_lock = threading.Lock()
is_speaking = threading.Event()

# ── Constants ─────────────────────────────────────────────────────────────────
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
WS_URL = "ws://127.0.0.1:8001/ws"
JARVIS_WS = WS_URL
WAKE_WORD = "jarvis"
WATCHDOG_TIMEOUT = 30
RESPONSE_TIMEOUT = 45
CRASH_LOG = "/tmp/voice_crash.log"

recognizer = sr.Recognizer()
recognizer.energy_threshold = 150
recognizer.dynamic_energy_threshold = False
recognizer.pause_threshold = 0.6
recognizer.non_speaking_duration = 0.3


# ── Crash logging ─────────────────────────────────────────────────────────────
def _log_crash(exc: Exception, context: str = ""):
    timestamp = datetime.now().isoformat()
    label = f" ({context})" if context else ""
    tb = traceback.format_exc()
    entry = (
        f"[{timestamp}] CRASH{label}: {type(exc).__name__}: {exc}\n"
        f"{tb}\n"
    )
    try:
        with open(CRASH_LOG, "a") as f:
            f.write(entry)
    except Exception:
        pass
    print(f"[System] {entry.strip()}")


# Keep backward-compatible alias
def log_crash(exc: Exception, context: str = ""):
    _log_crash(exc, context)


# ── Text helpers ──────────────────────────────────────────────────────────────
def sanitize_for_speech(text):
    text = re.sub(r'```.*?```', ' code snippet removed. ', text, flags=re.DOTALL)
    text = text.replace('`', '').replace('*', '').replace('@', ' at ')
    text = re.sub(r'http\S+', 'a link', text)
    return text.strip()


def truncate_to_sentences(text, n=2):
    """Return first n sentences of text."""
    parts = re.split(r'(?<=[.!?])\s+|\n', text.strip())
    return ' '.join(parts[:n])


# ── TTS / speak ───────────────────────────────────────────────────────────────
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


# ── STT helper ────────────────────────────────────────────────────────────────
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


# ── Coroutine 1: audio_producer ───────────────────────────────────────────────
async def audio_producer(audio_q: asyncio.Queue):
    """Continuously reads mic, puts raw frames into audio_q. Always runs."""
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
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
                try:
                    # Acquire gpu_lock with 10s timeout so mic never stalls indefinitely
                    lock_acquired = False
                    try:
                        await asyncio.wait_for(gpu_lock.acquire(), timeout=10)
                        lock_acquired = True
                    except asyncio.TimeoutError:
                        warn_msg = "[Warning] gpu_lock timeout in audio_producer — continuing without lock"
                        print(warn_msg)
                        try:
                            with open(CRASH_LOG, "a") as _f:
                                _f.write(f"[{datetime.now().isoformat()}] {warn_msg}\n")
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

                    # Drop oldest frame if queue is full
                    if audio_q.full():
                        try:
                            audio_q.get_nowait()
                            print("[Queue] audio_q full — dropped oldest frame")
                        except asyncio.QueueEmpty:
                            pass
                    await audio_q.put(audio)

                except Exception as e:
                    _log_crash(e, context="audio_producer")
                    await asyncio.sleep(1)


# ── Coroutine 2: transcription_consumer ──────────────────────────────────────
async def transcription_consumer(audio_q: asyncio.Queue, command_q: asyncio.Queue):
    """Reads audio_q, transcribes with Whisper, detects wake word, puts commands in command_q."""
    loop = asyncio.get_running_loop()
    while True:
        try:
            try:
                audio = await asyncio.wait_for(audio_q.get(), timeout=5)
            except asyncio.TimeoutError:
                continue

            if audio is None:
                continue

            # Interrupt TTS if currently speaking so mic is always responsive
            if is_speaking.is_set():
                subprocess.run(["pkill", "afplay"], capture_output=True)
                is_speaking.clear()
                await asyncio.sleep(0.1)

            try:
                text = await loop.run_in_executor(None, transcribe_audio, audio)
            except Exception as e:
                _log_crash(e, context="transcription_consumer_transcribe")
                continue

            if not text:
                continue

            print(f"\n[You] {text}")

            # Kill-switch command — bypass wake word
            if any(w in text for w in ["stop", "cancel", "abort"]):
                print("[Ears] Kill switch detected.")
                await command_q.put({"type": "stop"})
                continue

            # Wake word detection
            if WAKE_WORD in text:
                command = text.split(WAKE_WORD, 1)[1].strip()
                if command:
                    print(f"[Ears] Command detected: {command}")
                    await command_q.put({"type": "command", "text": command})
                else:
                    print("[Ears] Wake word heard, no command.")

        except Exception as e:
            _log_crash(e, context="transcription_consumer")
            await asyncio.sleep(1)


# ── Coroutine 3: command_processor ───────────────────────────────────────────
async def command_processor(command_q: asyncio.Queue, response_q: asyncio.Queue, ws):
    """Reads command_q, plays Tink.aiff, sends to Jarvis WS, enforces 45s watchdog."""
    waiting_since = [None]
    final_received = asyncio.Event()

    async def _watchdog():
        """Background task: resets waiting state after RESPONSE_TIMEOUT seconds."""
        while True:
            await asyncio.sleep(1)
            if waiting_since[0] is not None:
                elapsed = time.monotonic() - waiting_since[0]
                if elapsed > RESPONSE_TIMEOUT:
                    msg = f"[Watchdog] No 'final' from Jarvis within {RESPONSE_TIMEOUT}s — resetting state."
                    print(msg)
                    try:
                        with open(CRASH_LOG, "a") as _f:
                            _f.write(f"[{datetime.now().isoformat()}] {msg}\n")
                    except Exception:
                        pass
                    waiting_since[0] = None
                    final_received.set()

    asyncio.create_task(_watchdog())

    while True:
        try:
            try:
                item = await asyncio.wait_for(command_q.get(), timeout=5)
            except asyncio.TimeoutError:
                continue

            if item is None:
                continue

            if item.get("type") == "stop":
                print("[Command] Stop/cancel command — sending SYSTEM_COMMAND_STOP")
                try:
                    await ws.send(json.dumps({"message": "SYSTEM_COMMAND_STOP", "source": "voice"}))
                except Exception as e:
                    _log_crash(e, context="command_processor_stop_send")
                waiting_since[0] = None
                final_received.set()
                continue

            if item.get("type") == "command":
                command_text = item["text"]
                # Play Tink.aiff as immediate feedback (< 1s target)
                subprocess.run(["afplay", "/System/Library/Sounds/Tink.aiff"],
                               capture_output=True, timeout=3)
                print(f"[Ears] → Brain: {command_text}")
                try:
                    await ws.send(json.dumps({"message": command_text, "source": "voice"}))
                except Exception as e:
                    _log_crash(e, context="command_processor_send")
                    continue
                # Start 45s watchdog timer
                waiting_since[0] = time.monotonic()
                final_received.clear()

        except Exception as e:
            _log_crash(e, context="command_processor")
            await asyncio.sleep(1)


# ── Coroutine 4: tts_player ───────────────────────────────────────────────────
async def tts_player(response_q: asyncio.Queue):
    """Reads response_q, generates TTS, plays audio."""
    loop = asyncio.get_running_loop()
    while True:
        try:
            try:
                text = await asyncio.wait_for(response_q.get(), timeout=5)
            except asyncio.TimeoutError:
                continue

            if not text:
                continue

            print(f"[TTS] Rendering response...")
            await loop.run_in_executor(None, speak_text, text)

        except Exception as e:
            _log_crash(e, context="tts_player")
            await asyncio.sleep(1)


# ── Coroutine 5: ws_receiver ──────────────────────────────────────────────────
async def ws_receiver(ws, response_q: asyncio.Queue):
    """Receives messages from Jarvis WS, puts final responses in response_q."""
    while True:
        try:
            async for message in ws:
                try:
                    data = json.loads(message)
                    if "msg" in data:
                        print(f"\n[JARVIS] {data['msg'][:120]}")
                    if data.get("type") == "final":
                        # Queue response for TTS; drop if full
                        if response_q.full():
                            try:
                                response_q.get_nowait()
                                print("[Queue] response_q full — dropped oldest response")
                            except asyncio.QueueEmpty:
                                pass
                        await response_q.put(data["msg"])
                except Exception as e:
                    _log_crash(e, context="ws_receiver_parse")
        except Exception as e:
            _log_crash(e, context="ws_receiver")
            await asyncio.sleep(1)
            # Re-raise so main() reconnect loop can handle WS disconnects
            raise


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    audio_q    = asyncio.Queue(maxsize=10)
    command_q  = asyncio.Queue(maxsize=3)
    response_q = asyncio.Queue(maxsize=5)

    async with websockets.connect(JARVIS_WS, ping_interval=None) as ws:
        print("[System] Link established. JARVIS is online.")
        # Play startup sound to confirm connection
        subprocess.run(["afplay", "/System/Library/Sounds/Tink.aiff"], timeout=3)

        await asyncio.gather(
            audio_producer(audio_q),
            transcription_consumer(audio_q, command_q),
            command_processor(command_q, response_q, ws),
            tts_player(response_q),
            ws_receiver(ws, response_q),
        )


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\n[Ears] Shutting down.")
            sys.exit(0)
        except Exception as e:
            _log_crash(e, context="main_loop")
            subprocess.run(["afplay", "/System/Library/Sounds/Basso.aiff"], timeout=3)
            time.sleep(3)
