"""
gesture_daemon.py — Phase 6 v5 (pinch drag — tab focused)

Designed for one job: grab a browser tab with a pinch and drag it
to another window or screen.

HOW IT WORKS
────────────
  Index fingertip  →  cursor position (smoothed)
  Pinch (thumb + index close)  →  mouseDown  (grab the tab)
  Move while pinched           →  drag
  Release pinch                →  mouseUp    (drop)
  Open palm                    →  emergency cancel

WHY PINCH INSTEAD OF DWELL
───────────────────────────
  Dwell requires holding still *on* a 30px tab for 500ms with a
  hovering hand — too much precision demand. Pinch is an intentional
  physical action, low false-positive, and feels natural for dragging.

CAMERA TILT FIX
───────────────
  Set CAMERA_TILT_DEG to the approximate clockwise tilt of your
  webcam in degrees (e.g. 15, 30). Landmarks are rotated back before
  any geometry check so finger-up/down logic stays correct.

TUNING KEYS (in preview window)
───────────────────────────────
  +/-  adjust pinch threshold
  Q    quit

Requires: ~/cowork/hand_landmarker.task
Install:  pip install pyautogui opencv-python mediapipe websockets numpy
"""

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from mediapipe.tasks.python.vision import RunningMode
import pyautogui
import asyncio
import websockets
import json
import time
import math
import threading
from collections import deque
import os
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────

MODEL_PATH       = os.path.expanduser("~/cowork/hand_landmarker.task")
CANTIVIA_BUS_URL = "ws://localhost:8002"
CAMERA_INDEX     = 0
FRAME_W, FRAME_H = 640, 480

# ★ Set this to your webcam's clockwise tilt in degrees.
# If your camera is tilted left (top leans left), use a negative value.
# Start with 0, increase in steps of 10 until finger-up detection feels right.
CAMERA_TILT_DEG  = 40

# Pinch: thumb tip ↔ index tip normalised distance to count as "pinched"
PINCH_CLOSE      = 0.055   # below this = pinched (grab)
PINCH_OPEN       = 0.085   # above this = released (drop)  — hysteresis band

# Cursor smoothing
SMOOTH_FRAMES    = 8
VELOCITY_GATE    = 0.002   # normalised — below this = hand is still, don't jitter
DEAD_ZONE_PX     = 4

# How many frames of open palm to trigger cancel
PALM_FRAMES      = 8

pyautogui.FAILSAFE = False
pyautogui.PAUSE    = 0

# ── Landmark indices ──────────────────────────────────────────────────────────

WRIST      = 0
THUMB_TIP  = 4
INDEX_MCP  = 5
INDEX_TIP  = 8
MIDDLE_MCP = 9
MIDDLE_TIP = 12
RING_MCP   = 13
RING_TIP   = 16
PINKY_MCP  = 17
PINKY_TIP  = 20

# ── Multi-monitor ─────────────────────────────────────────────────────────────

def get_desktop():
    try:
        from AppKit import NSScreen
        screens = NSScreen.screens()
        min_x = min(s.frame().origin.x for s in screens)
        min_y = min(s.frame().origin.y for s in screens)
        max_x = max(s.frame().origin.x + s.frame().size.width  for s in screens)
        max_y = max(s.frame().origin.y + s.frame().size.height for s in screens)
        w, h = int(max_x - min_x), int(max_y - min_y)
        print(f"Desktop: {w}x{h} across {len(screens)} screen(s)")
        for i, s in enumerate(screens):
            f = s.frame()
            print(f"  [{i}] {int(f.size.width)}x{int(f.size.height)} @ ({int(f.origin.x)},{int(f.origin.y)})")
        return w, h, int(min_x), int(min_y)
    except Exception:
        w, h = pyautogui.size()
        print(f"Single screen {w}x{h}")
        return w, h, 0, 0

DESK_W, DESK_H, DESK_X, DESK_Y = get_desktop()

# ── Shared state ──────────────────────────────────────────────────────────────

latest_landmarks = None
landmarks_lock   = threading.Lock()

# ── Tilt correction ───────────────────────────────────────────────────────────

def rotate_landmarks(lms, deg):
    """
    Rotate all landmarks around the hand's centroid by -deg degrees.
    This compensates for a tilted camera so that 'up' in the image
    matches 'up' in the geometry checks.
    """
    if deg == 0:
        return lms

    rad = math.radians(-deg)  # counter-rotate to undo the tilt
    cos_r, sin_r = math.cos(rad), math.sin(rad)

    # Centroid of all landmarks
    cx = sum(l.x for l in lms) / len(lms)
    cy = sum(l.y for l in lms) / len(lms)

    class LM:
        __slots__ = ('x', 'y', 'z')
        def __init__(self, x, y, z):
            self.x, self.y, self.z = x, y, z

    rotated = []
    for l in lms:
        dx, dy = l.x - cx, l.y - cy
        rx = cx + dx * cos_r - dy * sin_r
        ry = cy + dx * sin_r + dy * cos_r
        rotated.append(LM(rx, ry, l.z))
    return rotated

# ── Gesture helpers ───────────────────────────────────────────────────────────

def dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)

def pinch_distance(lms):
    return dist(lms[THUMB_TIP], lms[INDEX_TIP])

def is_open_palm(lms):
    tips = [INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP]
    mcps = [INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP]
    fingers = sum(1 for t, m in zip(tips, mcps) if lms[t].y < lms[m].y - 0.03)
    return fingers >= 4 and dist(lms[THUMB_TIP], lms[INDEX_MCP]) > 0.06

# ── Pinch state ───────────────────────────────────────────────────────────────

class PinchState:
    def __init__(self):
        self.pos_history  = deque(maxlen=SMOOTH_FRAMES)
        self.prev_raw     = None
        self.last_cursor  = (0, 0)

        self.pinched      = False   # currently holding mouseDown
        self.mode         = "idle"  # idle | pinched | dragging
        self.palm_count   = 0
        self.last_pub     = None
        self.pinch_dist   = 0.0     # for HUD display

ps = PinchState()

# ── Cursor ────────────────────────────────────────────────────────────────────

def get_cursor(lms):
    tip = lms[INDEX_TIP]
    raw_x = int(tip.x * DESK_W) + DESK_X
    raw_y = int(tip.y * DESK_H) + DESK_Y
    raw_x = max(DESK_X, min(DESK_X + DESK_W - 1, raw_x))
    raw_y = max(DESK_Y, min(DESK_Y + DESK_H - 1, raw_y))

    if ps.prev_raw:
        vx = abs(tip.x - ps.prev_raw[0])
        vy = abs(tip.y - ps.prev_raw[1])
        if vx < VELOCITY_GATE and vy < VELOCITY_GATE:
            return ps.last_cursor
    ps.prev_raw = (tip.x, tip.y)

    ps.pos_history.append((raw_x, raw_y))
    n = len(ps.pos_history)
    weights = list(range(1, n + 1))
    wsum = sum(weights)
    sx = int(sum(w * p[0] for w, p in zip(weights, ps.pos_history)) / wsum)
    sy = int(sum(w * p[1] for w, p in zip(weights, ps.pos_history)) / wsum)

    lx, ly = ps.last_cursor
    if abs(sx - lx) <= DEAD_ZONE_PX and abs(sy - ly) <= DEAD_ZONE_PX:
        return ps.last_cursor

    ps.last_cursor = (sx, sy)
    return sx, sy

# ── Pinch engine ──────────────────────────────────────────────────────────────

def pinch_tick(lms, cx, cy):
    """
    Simple two-state pinch machine with hysteresis.
    Returns mode string for HUD.
    """
    d = pinch_distance(lms)
    ps.pinch_dist = d

    if not ps.pinched:
        # Waiting for pinch
        if d < PINCH_CLOSE:
            ps.pinched = True
            ps.mode    = "pinched"
            pyautogui.mouseDown()
        else:
            ps.mode = "idle"
    else:
        # Currently pinched — check for release
        if d > PINCH_OPEN:
            ps.pinched = False
            pyautogui.mouseUp()
            ps.mode = "idle"
            return "dropped"
        else:
            # Still pinched — are we moving?
            ps.mode = "dragging"

    return ps.mode

def emergency_cancel():
    if ps.pinched:
        pyautogui.mouseUp()
        ps.pinched = False
    ps.mode      = "idle"
    ps.palm_count = 0

# ── Bus ───────────────────────────────────────────────────────────────────────

_bus_loop      = None
_bus_connected = False

def publish(name):
    if _bus_loop and name != ps.last_pub:
        asyncio.run_coroutine_threadsafe(_send(name), _bus_loop)
        ps.last_pub = name

async def _send(name):
    global _bus_connected
    try:
        async with websockets.connect(CANTIVIA_BUS_URL, open_timeout=2) as ws:
            await ws.send(json.dumps({"type": "GESTURE_EVENT", "gesture": name, "ts": time.time()}))
            _bus_connected = True
    except Exception:
        _bus_connected = False

def start_bus():
    global _bus_loop
    loop = asyncio.new_event_loop()
    _bus_loop = loop
    threading.Thread(target=loop.run_forever, daemon=True).start()

# ── MediaPipe callback ────────────────────────────────────────────────────────

def on_result(result, output_image, timestamp_ms):
    global latest_landmarks
    with landmarks_lock:
        latest_landmarks = result.hand_landmarks[0] if result.hand_landmarks else None

# ── Draw HUD ──────────────────────────────────────────────────────────────────

def draw_hud(frame, lms, mode):
    color_map = {
        "idle":     (80, 200, 120),
        "pinched":  (80, 180, 255),
        "dragging": (255, 160, 40),
        "dropped":  (255, 255, 255),
        "cancel":   (80, 80, 255),
        "no hand":  (100, 100, 100),
    }
    col = color_map.get(mode, (180, 180, 180))

    # Mode label
    cv2.putText(frame, mode.upper(), (12, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, col, 2)

    if lms:
        # Index fingertip dot
        ix = int(lms[INDEX_TIP].x * FRAME_W)
        iy = int(lms[INDEX_TIP].y * FRAME_H)
        cv2.circle(frame, (ix, iy), 8, col, -1)

        # Thumb tip dot
        tx = int(lms[THUMB_TIP].x * FRAME_W)
        ty = int(lms[THUMB_TIP].y * FRAME_H)
        cv2.circle(frame, (tx, ty), 6, col, -1)

        # Line between thumb and index (shows pinch distance)
        cv2.line(frame, (ix, iy), (tx, ty), col, 1)

        # Pinch distance bar (bottom of frame)
        bar_w = int(ps.pinch_dist * 8 * FRAME_W)  # rough scale
        bar_w = min(bar_w, FRAME_W)
        close_px = int(PINCH_CLOSE * 8 * FRAME_W)
        open_px  = int(PINCH_OPEN  * 8 * FRAME_W)
        cv2.rectangle(frame, (0, FRAME_H - 18), (bar_w, FRAME_H - 8), col, -1)
        cv2.line(frame, (close_px, FRAME_H - 22), (close_px, FRAME_H - 4), (0, 255, 0), 1)
        cv2.line(frame, (open_px,  FRAME_H - 22), (open_px,  FRAME_H - 4), (0, 180, 255), 1)

    # Bottom status
    tilt_str = f"tilt:{CAMERA_TILT_DEG}°"
    cv2.putText(frame, f"pinch:{ps.pinch_dist:.3f}  {tilt_str}",
                (12, FRAME_H - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (140, 140, 140), 1)
    cv2.putText(frame, "bus:ok" if _bus_connected else "bus:off",
                (12, FRAME_H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (140, 140, 140), 1)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(MODEL_PATH):
        print(f"Model not found: {MODEL_PATH}")
        print('curl -L "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task" -o ~/cowork/hand_landmarker.task')
        return

    start_bus()

    opts = mp_vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=RunningMode.LIVE_STREAM,
        num_hands=1,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        result_callback=on_result
    )

    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)

    print(f"\nGesture daemon v5 — pinch drag")
    print(f"Desktop: {DESK_W}x{DESK_H}")
    print(f"Pinch close: {PINCH_CLOSE}  |  Pinch open: {PINCH_OPEN}")
    print(f"Camera tilt correction: {CAMERA_TILT_DEG}°")
    print(f"\nHow to use:")
    print(f"  Point index finger      → moves cursor")
    print(f"  Pinch (thumb+index)     → grab (mouseDown)")
    print(f"  Move while pinched      → drag the tab")
    print(f"  Open pinch              → drop (mouseUp)")
    print(f"  Open palm               → emergency cancel")
    print(f"\nTuning keys:")
    print(f"  +/-  adjust pinch threshold")
    print(f"  T/t  increase/decrease tilt correction")
    print(f"  Q    quit\n")

    with mp_vision.HandLandmarker.create_from_options(opts) as landmarker:
        ts = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            ts += 1
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB,
                              data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            landmarker.detect_async(mp_img, ts)

            with landmarks_lock:
                raw_lms = latest_landmarks

            mode = "no hand"

            if raw_lms:
                lms = rotate_landmarks(raw_lms, CAMERA_TILT_DEG)

                # Open palm → emergency cancel
                if is_open_palm(lms):
                    ps.palm_count += 1
                    if ps.palm_count >= PALM_FRAMES:
                        emergency_cancel()
                        publish("open_palm")
                        mode = "cancel"
                else:
                    ps.palm_count = 0
                    cx, cy = get_cursor(lms)
                    pyautogui.moveTo(cx, cy)
                    mode = pinch_tick(lms, cx, cy)
                    publish(mode)
            else:
                emergency_cancel()
                ps.pos_history.clear()
                ps.prev_raw = None

            draw_hud(frame, raw_lms, mode)
            cv2.imshow("Gesture v5 — pinch drag — Q to quit", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key in (ord('+'), ord('=')):
                globals()['PINCH_CLOSE'] = round(min(PINCH_CLOSE + 0.005, 0.15), 3)
                globals()['PINCH_OPEN']  = round(min(PINCH_OPEN  + 0.005, 0.18), 3)
                print(f"Pinch close: {PINCH_CLOSE}  open: {PINCH_OPEN}")
            elif key == ord('-'):
                globals()['PINCH_CLOSE'] = round(max(PINCH_CLOSE - 0.005, 0.02), 3)
                globals()['PINCH_OPEN']  = round(max(PINCH_OPEN  - 0.005, 0.04), 3)
                print(f"Pinch close: {PINCH_CLOSE}  open: {PINCH_OPEN}")
            elif key == ord('T'):
                globals()['CAMERA_TILT_DEG'] = CAMERA_TILT_DEG + 5
                print(f"Tilt: {CAMERA_TILT_DEG}°")
            elif key == ord('t'):
                globals()['CAMERA_TILT_DEG'] = CAMERA_TILT_DEG - 5
                print(f"Tilt: {CAMERA_TILT_DEG}°")

    emergency_cancel()
    cap.release()
    cv2.destroyAllWindows()
    print("Stopped.")

if __name__ == "__main__":
    main()
