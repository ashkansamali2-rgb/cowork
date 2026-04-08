import pvporcupine, pyaudio, struct, wave, whisper, subprocess
import sys, os, tempfile, threading
sys.path.insert(0, os.path.expanduser("~/jarvis"))
from config import PICOVOICE_KEY
from core.router import run

VOICE_MODEL = os.path.expanduser("~/jarvis/voices/en_GB-alan-medium.onnx")
SILENCE_THRESHOLD = 500
SILENCE_SECONDS = 2
active_branch = "general"
stop_speaking = threading.Event()
currently_speaking = threading.Event()

def speak(text: str):
    stop_speaking.clear()
    currently_speaking.set()
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
        subprocess.run(
            ["piper", "--model", VOICE_MODEL, "--output_file", wav_path],
            input=text[:250], capture_output=True, text=True
        )
        if not stop_speaking.is_set():
            proc = subprocess.Popen(["afplay", "-r", "1.25", wav_path])
            while proc.poll() is None:
                if stop_speaking.is_set():
                    proc.kill()
                    break
                threading.Event().wait(0.1)
        try:
            os.unlink(wav_path)
        except:
            pass
    except Exception as e:
        subprocess.run(["say", "-v", "Daniel", text[:250]])
    finally:
        currently_speaking.clear()

def transcribe(audio_path: str) -> str:
    model = whisper.load_model("base")
    result = model.transcribe(audio_path)
    return result["text"].strip()

def record_until_silence(stream, pa, frame_length) -> str:
    print("[Voice] Listening...")
    frames, silent = [], 0
    while True:
        data = stream.read(frame_length, exception_on_overflow=False)
        frames.append(data)
        samples = struct.unpack_from(f"{frame_length}h", data)
        volume = max(abs(s) for s in samples)
        silent = silent + 1 if volume < SILENCE_THRESHOLD else 0
        if silent > (16000 / frame_length * SILENCE_SECONDS):
            break
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    wf = wave.open(path, "wb")
    wf.setnchannels(1)
    wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
    wf.setframerate(16000)
    wf.writeframes(b"".join(frames))
    wf.close()
    return path

def is_stop_command(text: str) -> bool:
    t = text.lower().strip().rstrip("!.,?")
    return t in ["stop", "just stop", "cancel"]

def check_command(text: str):
    t = text.lower().strip()
    if "switch to coding" in t:
        return ("branch", "coding")
    if "switch to cad" in t:
        return ("branch", "cad")
    if "switch to general" in t:
        return ("branch", "general")
    if is_stop_command(text):
        return ("stop", None)
    return (None, None)

def interrupt_listener(porcupine, stream):
    while True:
        if currently_speaking.is_set():
            try:
                pcm = stream.read(porcupine.frame_length, exception_on_overflow=False)
                pcm = struct.unpack_from(f"{porcupine.frame_length}h", pcm)
                if porcupine.process(pcm) >= 0:
                    print("[Voice] Interrupted!")
                    frames, silent = [], 0
                    for _ in range(int(16000 / porcupine.frame_length * 3)):
                        data = stream.read(porcupine.frame_length, exception_on_overflow=False)
                        frames.append(data)
                        samples = struct.unpack_from(f"{porcupine.frame_length}h", data)
                        volume = max(abs(s) for s in samples)
                        silent = silent + 1 if volume < SILENCE_THRESHOLD else 0
                        if silent > (16000 / porcupine.frame_length * 1.5):
                            break
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        path = f.name
                    wf = wave.open(path, "wb")
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(b"".join(frames))
                    wf.close()
                    model = whisper.load_model("base")
                    text = model.transcribe(path)["text"].strip()
                    os.unlink(path)
                    print(f"[Voice] Interrupt: {text}")
                    if is_stop_command(text):
                        stop_speaking.set()
            except Exception:
                pass
        else:
            threading.Event().wait(0.1)

def main():
    global active_branch
    porcupine = pvporcupine.create(access_key=PICOVOICE_KEY, keywords=["jarvis"])
    pa = pyaudio.PyAudio()
    stream = pa.open(
        rate=porcupine.sample_rate, channels=1,
        format=pyaudio.paInt16, input=True,
        frames_per_buffer=porcupine.frame_length
    )
    print(f"[Voice] Ready. Say \"Hey Jarvis\". Branch: {active_branch}")
    speak("Jarvis online.")

    t = threading.Thread(target=interrupt_listener, args=(porcupine, stream), daemon=True)
    t.start()

    try:
        while True:
            if currently_speaking.is_set():
                threading.Event().wait(0.1)
                continue
            pcm = stream.read(porcupine.frame_length, exception_on_overflow=False)
            pcm = struct.unpack_from(f"{porcupine.frame_length}h", pcm)
            if porcupine.process(pcm) >= 0:
                print("[Voice] Wake word detected!")
                speak("Yes?")
                path = record_until_silence(stream, pa, porcupine.frame_length)
                text = transcribe(path)
                os.unlink(path)
                print(f"[Voice] You said: {text}")
                if not text or len(text.strip()) < 2:
                    speak("I didn't catch that.")
                    continue
                cmd_type, cmd_value = check_command(text)
                if cmd_type == "stop":
                    speak("Cancelled.")
                    continue
                if cmd_type == "branch":
                    active_branch = cmd_value
                    speak(f"Switched to {active_branch}.")
                    print(f"[Voice] Branch: {active_branch}")
                    continue
                task_text = text
                t_lower = text.lower()
                if "switch to coding" in t_lower and ("and" in t_lower or "then" in t_lower):
                    active_branch = "coding"
                    task_text = t_lower.split("and", 1)[-1].split("then", 1)[-1].strip()
                elif "switch to cad" in t_lower and ("and" in t_lower or "then" in t_lower):
                    active_branch = "cad"
                    task_text = t_lower.split("and", 1)[-1].split("then", 1)[-1].strip()

                def run_task(msg, branch):
                    result = run(msg, {"branch": branch})
                    full = result["result"]
                    print(f"[Voice] Jarvis: {full[:200]}")
                    first_line = full.split("\n")[0]
                    if not stop_speaking.is_set():
                        speak(first_line[:150])

                task_thread = threading.Thread(target=run_task, args=(task_text, active_branch))
                task_thread.start()

    except KeyboardInterrupt:
        print("[Voice] Stopped.")
    finally:
        stream.close()
        pa.terminate()
        porcupine.delete()

if __name__ == "__main__":
    main()
