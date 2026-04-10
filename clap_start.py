#!/usr/bin/env python3
import pyaudio, struct, math, time, os, subprocess

CHUNK = 1024
RATE = 44100
THRESHOLD = 3000
CLAP_WINDOW = 0.6
MIN_SILENCE = 0.1

COWORK = "/Users/ashkansamali/cowork"
START_SCRIPT = f"{COWORK}/start_cowork.sh"
STOP_PORTS = "8001,8002,8080,8081,5173"

def rms(data):
    shorts = struct.unpack('%dh' % (len(data) // 2), data)
    return math.sqrt(sum(s*s for s in shorts) / len(shorts))

def listen_for_double_clap():
    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                     input=True, frames_per_buffer=CHUNK)
    print("[Clap] Listening... double clap to start/stop Cowork")
    claps = []
    last_clap = 0
    in_clap = False
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        volume = rms(data)
        now = time.time()
        if volume > THRESHOLD and not in_clap and (now - last_clap) > MIN_SILENCE:
            in_clap = True
            claps.append(now)
            last_clap = now
            claps = [t for t in claps if now - t < CLAP_WINDOW]
            if len(claps) >= 2:
                claps = []
                stream.close()
                pa.terminate()
                return
        elif volume < THRESHOLD:
            in_clap = False

def start_cowork():
    print("[Clap] Starting Cowork via start_cowork.sh...")
    subprocess.Popen(
        ["/bin/zsh", START_SCRIPT],
        stdout=None,   # inherit terminal so coloured output is visible
        stderr=None,
    )

def stop_cowork():
    print("[Clap] Stopping Cowork...")
    os.system(f"lsof -ti:{STOP_PORTS} | xargs kill -9 2>/dev/null")
    os.system("pkill -f cantivia && pkill -f llama-server && pkill -f live_voice && pkill -f api_server 2>/dev/null")
    print("[Clap] Cowork stopped.")

running = False
while True:
    listen_for_double_clap()
    if not running:
        start_cowork()
        running = True
    else:
        stop_cowork()
        running = False
