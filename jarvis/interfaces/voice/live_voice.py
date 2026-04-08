import asyncio
import os
os.environ["HF_HUB_OFFLINE"] = "1"
import websockets
import json
import speech_recognition as sr
import sys
import concurrent.futures
import tempfile
import mlx_whisper
import soundfile as sf
import numpy as np
import re
import threading
import random

# --- THE TRAFFIC LIGHT ---
gpu_lock = threading.Lock()

# --- 1. THE EARS (Whisper) ---
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
recognizer = sr.Recognizer()
recognizer.energy_threshold = 150 
recognizer.dynamic_energy_threshold = False 
recognizer.pause_threshold = 2.0

# --- 2. THE VOICE (Qwen3-TTS) ---
from mlx_audio.tts.utils import load_model
print("[System] Booting Qwen3-TTS Vocal Engine...")
tts_model = load_model("mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16")

JARVIS_AUDIO_PATH = os.path.expanduser("~/jarvis/jarvis.wav")
JARVIS_AUDIO_TEXT = "Sir, I've detected an anomaly in the primary power grid. Current efficiency is at 78.3%, suggesting a potential optimization requirement. Shall I begin diagnostic protocols and prepare contingency measures for your review?"

GREETINGS = [
    "Systems are fully online, sir. How can I assist you?",
    "Good to see you, sir. Awaiting your command.",
    "Boot sequence complete. What is on the agenda for today?",
    "I am online and ready, sir.",
    "Facility secure. Neural network is spooled up. How can I help?"
]

def sanitize_for_speech(text):
    text = re.sub(r'```.*?```', ' code snippet removed. ', text, flags=re.DOTALL)
    text = text.replace('`', '').replace('*', '').replace('@', ' at ')
    text = re.sub(r'http\S+', 'a link', text)
    return text.strip()

def speak_text(text):
    safe_text = sanitize_for_speech(text)
    print(f"[Voice] Synthesizing: {safe_text}")
    try:
        with gpu_lock:
            results = list(tts_model.generate(
                text=safe_text, 
                ref_audio=JARVIS_AUDIO_PATH,
                ref_text=JARVIS_AUDIO_TEXT,
                language="English"
            ))
            audio_array = results[0].audio
            
            # VOLUME BOOST: Multiply by 1.8 and clip to prevent distortion
            amplified_audio = np.clip(np.array(audio_array) * 1.8, -1.0, 1.0)
            
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            
        sf.write(tmp_path, amplified_audio, 24000) 
        os.system(f"afplay {tmp_path}")
        os.remove(tmp_path)
    except Exception as e:
        print(f"[Voice Error] {e} -> Falling back to Daniel.")
        clean_text = safe_text.replace("'", "").replace('"', "")
        os.system(f"say -v Daniel '{clean_text}' &")

# --- 3. THE NERVOUS SYSTEM (WebSocket) ---
WS_URL = "ws://127.0.0.1:8001/ws"
WAKE_WORD = "jarvis"

async def listen_and_send():
    print(f"[System] Connecting to Brain ({WS_URL})...")
    try:
        async with websockets.connect(WS_URL, ping_interval=None) as ws:
            print("[System] Link Established! JARVIS is fully online.")
            
            async def receive_updates():
                try:
                    async for message in ws:
                        data = json.loads(message)
                        if "msg" in data:
                            print(f"\n[JARVIS] {data['msg']}")
                        if data.get("type") == "final":
                            speak_text(data["msg"])
                except Exception as e:
                    pass

            asyncio.create_task(receive_updates())
            
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                with sr.Microphone() as source:
                    print("\n[Mic] Calibrating...")
                    recognizer.adjust_for_ambient_noise(source, duration=1)
                    print(f"[Mic] Online. Ready for your command.")
                    
                    # Randomly pick a greeting and speak it once the mic is ready
                    greeting = random.choice(GREETINGS)
                    await asyncio.to_thread(speak_text, greeting)

                    while True:
                        def get_audio():
                            try:
                                audio = recognizer.listen(source)
                                if gpu_lock.locked():
                                    return None
                                    
                                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                                    f.write(audio.get_wav_data())
                                    tmp_path = f.name
                                    
                                with gpu_lock:
                                    result = mlx_whisper.transcribe(tmp_path, path_or_hf_repo=WHISPER_MODEL)
                                    
                                os.remove(tmp_path)
                                return result["text"].lower()
                            except Exception as e:
                                return None

                        text = await loop.run_in_executor(pool, get_audio)
                        
                        if text:
                            print(f"\n[You] Heard: {text}")
                            
                            if any(word in text for word in ["stop", "cancel", "abort"]):
                                print("[Ears] KILL SWITCH TRIGGERED.")
                                await ws.send(json.dumps({"type": "prompt", "msg": "SYSTEM_COMMAND_STOP"}))
                                continue
                                
                            if WAKE_WORD in text:
                                command = text.split(WAKE_WORD, 1)[1].strip()
                                if command:
                                    print(f"[Ears] Sending to Brain: {command}")
                                    await ws.send(json.dumps({"type": "prompt", "msg": command}))
                                else:
                                    print("[Ears] Heard wake word, but no command.")
    except Exception as e:
        print(f"[System] Connection Failed: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(listen_and_send())
    except KeyboardInterrupt:
        print("\n[Ears] Shutting down.")
        sys.exit(0)
