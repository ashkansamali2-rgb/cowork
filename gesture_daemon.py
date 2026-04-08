"""
gesture_daemon.py — Phase 6 v4 (dwell click — daily driver)

How it works:
- Index fingertip drives the cursor. No gesture classification.
- Dwell click: hold still for DWELL_MS → mouseDown
- Dwell release: hold still again for DWELL_MS → mouseUp (completes drag)
- Two fingers up + move → scroll
- Open palm (hold 8 frames) → cancel / mouseUp emergency

Tab dragging:
  1. Point at tab, hold still → grabs it
  2. Move finger → drags tab across
  3. Hold still → drops it

Requires: ~/cowork/hand_landmarker.task
Install:   pip install pyautogui opencv-python mediapipe websockets
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

# ── Config ────────────────────────────────────────────────────────────────────

MODEL_PATH       = os.path.expanduser("~/cowork/hand_landmarker.task")
CANTIVIA_BUS_URL = "ws://localhost:8002"
CAMERA_INDEX     = 0
FRAME_W, FRAME_H = 640, 480

DWELL_MS         = 500    # ms of stillness to fire mouseDown or mouseUp
DWELL_MOVE_PX    = 18     # pixels — if cursor moves more than this, reset dwell timer
DRAG_MOVE_PX     = 14     # pixels — movement needed to enter drag mode

SMOOTH_FRAMES    = 10     # weighted smoothing window
VELOCITY_GATE    = 0.003  # normalized — below this = hand is "still"
DEAD_ZONE_PX     = 5      # don't move cursor for tiny hand movements

SCROLL_FINGERS   = 2      # how many fingers up = scroll mode
SCROLL_DEAD      = 0.003  # minimum motion to scroll
SCROLL_SCALE     = 14     # lower = faster

PALM_FRAMES      = 10     # open palm must be held this many frames to cancel

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
    except Exception as e:
        w, h = pyautogui.size()
        print(f"Single screen {w}x{h}")
        return w, h, 0, 0

DESK_W, DESK_H, DESK_X, DESK_Y = get_desktop()

# ── Shared state ──────────────────────────────────────────────────────────────

latest_landmarks = None
landmarks_lock   = threading.Lock()

# ── Dwell state machine ───────────────────────────────────────────────────────
#
#   IDLE ──(still DWELL_MS)──► PRESSING ──(mouseDown)──► DOWN
#   DOWN ──(moved > DRAG_PX)──► DRAGGING
#   DRAGGING ──(still DWELL_MS)──► RELEASING ──(mouseUp)──► IDLE
#   DOWN ──(still DWELL_MS, no drag)──► RELEASING ──(mouseUp + click)──► IDLE
#   any state ──(open palm)──► IDLE (emergency cancel)

class DwellState:
    def __init__(self):
        # Cursor smoothing
        self.pos_history   = deque(maxlen=SMOOTH_FRAMES)
        self.prev_raw      = None
        self.last_cursor   = (0, 0)

        # Dwell
        self.dwell_start   = None     # time when hand became still
        self.dwell_anchor  = None     # cursor position when dwell started
        self.mouse_down    = False
        self.dragging      = False
        self.drag_origin   = None
        self.mode          = "idle"   # idle | pressing | down | dragging | releasing

        # Scroll
        self.scroll_buf    = deque(maxlen=5)
        self.prev_scroll_y = None

        # Palm cancel
        self.palm_count    = 0

        # Bus
        self.last_pub      = None

ds = DwellState()

# ── Math ──────────────────────────────────────────────────────────────────────

def dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)

def fingers_up_count(lms):
    tips = [INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP]
    mcps = [INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP]
    return sum(1 for t, m in zip(tips, mcps) if lms[t].y < lms[m].y - 0.03)

def is_open_palm(lms):
    return fingers_up_count(lms) >= 4 and dist(lms[THUMB_TIP], lms[INDEX_MCP]) > 0.06

def is_scroll_mode(lms):
    index_up  = lms[INDEX_TIP].y  < lms[INDEX_MCP].y  - 0.03
    middle_up = lms[MIDDLE_TIP].y < lms[MIDDLE_MCP].y - 0.03
    ring_dn   = lms[RING_TIP].y   > lms[RING_MCP].y
    pinky_dn  = lms[PINKY_TIP].y  > lms[PINKY_MCP].y
    return index_up and middle_up and ring_dn and pinky_dn

# ── Cursor: index fingertip → screen ─────────────────────────────────────────

def get_cursor(lms):
    """
    Map index fingertip directly to screen coords.
    Weighted smoothing + velocity gate + dead zone.
    """
    tip = lms[INDEX_TIP]
    raw_x = int((1.0 - tip.x) * DESK_W) + DESK_X
    raw_y = int(tip.y * DESK_H) + DESK_Y
    raw_x = max(DESK_X, min(DESK_X + DESK_W - 1, raw_x))
    raw_y = max(DESK_Y, min(DESK_Y + DESK_H - 1, raw_y))

    # Velocity gate
    if ds.prev_raw:
        vx = abs(tip.x - ds.prev_raw[0])
        vy = abs(tip.y - ds.prev_raw[1])
        if vx < VELOCITY_GATE and vy < VELOCITY_GATE:
            return ds.last_cursor
    ds.prev_raw = (tip.x, tip.y)

    ds.pos_history.append((raw_x, raw_y))
    n = len(ds.pos_history)
    weights = list(range(1, n + 1))
    wsum = sum(weights)
    sx = int(sum(w * p[0] for w, p in zip(weights, ds.pos_history)) / wsum)
    sy = int(sum(w * p[1] for w, p in zip(weights, ds.pos_history)) / wsum)

    lx, ly = ds.last_cursor
    if abs(sx - lx) <= DEAD_ZONE_PX and abs(sy - ly) <= DEAD_ZONE_PX:
        return ds.last_cursor

    ds.last_cursor = (sx, sy)
    return sx, sy

# ── Dwell engine ──────────────────────────────────────────────────────────────

def dwell_tick(cx, cy):
    """
    Core dwell state machine. Call every frame with current cursor pos.
    Returns (mode, dwell_progress_0_to_1)
    """
    now = time.time()

    # How far has cursor moved since dwell started?
    if ds.dwell_anchor:
        ax, ay = ds.dwell_anchor
        moved = math.hypot(cx - ax, cy - ay)
    else:
        moved = 0

    # If hand moved significantly, reset dwell timer
    if moved > DWELL_MOVE_PX:
        ds.dwell_start  = now
        ds.dwell_anchor = (cx, cy)
        # If we're in drag mode, that's fine — cursor is supposed to move
        if ds.mode == "dragging":
            return ds.mode, 0.0
        # Otherwise cancel any building dwell
        if ds.mode in ("pressing", "releasing"):
            ds.mode = "down" if ds.mouse_down else "idle"
        return ds.mode, 0.0

    # Start dwell timer if not running
    if ds.dwell_start is None or ds.dwell_anchor is None:
        ds.dwell_start  = now
        ds.dwell_anchor = (cx, cy)

    elapsed  = now - ds.dwell_start
    progress = min(elapsed / (DWELL_MS / 1000), 1.0)

    # ── State transitions ──

    if ds.mode == "idle":
        if progress >= 1.0:
            # Dwell complete → press down
            pyautogui.mouseDown()
            ds.mouse_down  = True
            ds.drag_origin = (cx, cy)
            ds.mode        = "down"
            ds.dwell_start = None
            return "down", 1.0
        return "idle", progress

    elif ds.mode == "down":
        # Check if we've started dragging
        if ds.drag_origin:
            dx = abs(cx - ds.drag_origin[0])
            dy = abs(cy - ds.drag_origin[1])
            if dx > DRAG_MOVE_PX or dy > DRAG_MOVE_PX:
                ds.mode        = "dragging"
                ds.dwell_start = None
                return "dragging", 0.0
        # Still down and still — count towards release dwell
        if progress >= 1.0:
            # Quick click (no drag) — release and click
            pyautogui.mouseUp()
            pyautogui.click()
            ds.mouse_down  = False
            ds.drag_origin = None
            ds.mode        = "idle"
            ds.dwell_start = None
            return "clicked", 1.0
        return "down", progress

    elif ds.mode == "dragging":
        # Dragging — cursor follows finger, dwell to drop
        if progress >= 1.0:
            pyautogui.mouseUp()
            ds.mouse_down  = False
            ds.dragging    = False
            ds.drag_origin = None
            ds.mode        = "idle"
            ds.dwell_start = None
            return "dropped", 1.0
        return "dragging", progress

    return ds.mode, progress

def emergency_cancel():
    """Open palm — release everything immediately."""
    if ds.mouse_down:
        pyautogui.mouseUp()
        ds.mouse_down  = False
    ds.dragging    = False
    ds.drag_origin = None
    ds.mode        = "idle"
    ds.dwell_start = None
    ds.dwell_anchor= None

# ── Scroll ────────────────────────────────────────────────────────────────────

def do_scroll(lms):
    mid_y = (lms[INDEX_TIP].y + lms[MIDDLE_TIP].y) / 2
    if ds.prev_scroll_y is not None:
        delta = mid_y - ds.prev_scroll_y
        ds.scroll_buf.append(delta)
        avg = sum(ds.scroll_buf) / len(ds.scroll_buf)
        if abs(avg) > SCROLL_DEAD:
            mag = min(abs(avg) * 500, 25)
            pyautogui.scroll(int(-math.copysign(mag, avg)))
    ds.prev_scroll_y = mid_y

# ── Bus ───────────────────────────────────────────────────────────────────────

_bus_loop = None
_bus_connected = False

def publish(name):
    if _bus_loop and name != ds.last_pub:
        asyncio.run_coroutine_threadsafe(_send(name), _bus_loop)
        ds.last_pub = name

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

# ── Draw dwell arc on preview ─────────────────────────────────────────────────

def draw_dwell_arc(frame, cx_norm, cy_norm, progress, mode):
    """Draw a circular progress arc around the fingertip in the preview window."""
    px = int((1 - cx_norm) * FRAME_W)
    py = int(cy_norm * FRAME_H)

    color_map = {
        "idle":     (80, 200, 120),   # green building
        "down":     (80, 180, 255),   # blue — held down
        "dragging": (255, 160, 40),   # orange — dragging
        "clicked":  (255, 255, 255),
        "dropped":  (255, 255, 255),
    }
    col = color_map.get(mode, (180, 180, 180))

    # Background ring
    cv2.circle(frame, (px, py), 22, (60, 60, 60), 1)

    # Progress arc (approximate with polyline)
    if progress > 0:
        pts = []
        steps = max(2, int(progress * 32))
        for i in range(steps + 1):
            angle = -math.pi / 2 + (i / 32) * 2 * math.pi * progress
            ex = int(px + 22 * math.cos(angle))
            ey = int(py + 22 * math.sin(angle))
            pts.append([ex, ey])
        if len(pts) >= 2:
            import numpy as np
            cv2.polylines(frame, [np.array(pts)], False, col, 2)

    # Dot at fingertip
    cv2.circle(frame, (px, py), 6, col, -1)

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

    print(f"\nGesture daemon v4 — dwell click")
    print(f"Desktop: {DESK_W}x{DESK_H}")
    print(f"Dwell time: {DWELL_MS}ms  |  Move threshold: {DWELL_MOVE_PX}px")
    print(f"\nHow to use:")
    print(f"  Point index finger  → moves cursor")
    print(f"  Hold still {DWELL_MS}ms     → click (or grab for drag)")
    print(f"  Move while grabbed  → drags (tab dragging works!)")
    print(f"  Hold still again    → drop")
    print(f"  2 fingers + move    → scroll")
    print(f"  Open palm           → cancel / release\n")

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
                lms = latest_landmarks

            mode = "no hand"
            progress = 0.0

            if lms:
                # Open palm → emergency cancel
                if is_open_palm(lms):
                    ds.palm_count += 1
                    if ds.palm_count >= PALM_FRAMES:
                        emergency_cancel()
                        publish("open_palm")
                        mode = "cancel"
                else:
                    ds.palm_count = 0

                # Scroll mode — 2 fingers up
                if is_scroll_mode(lms) and not ds.mouse_down:
                    do_scroll(lms)
                    publish("scroll")
                    mode = "scroll"
                    # Draw both fingertips
                    for idx in [INDEX_TIP, MIDDLE_TIP]:
                        px = int((1 - lms[idx].x) * FRAME_W)
                        py = int(lms[idx].y * FRAME_H)
                        cv2.circle(frame, (px, py), 7, (80, 200, 120), -1)
                else:
                    ds.prev_scroll_y = None

                    # Normal mode — index fingertip drives cursor
                    cx, cy = get_cursor(lms)
                    pyautogui.moveTo(cx, cy)
                    mode, progress = dwell_tick(cx, cy)
                    publish(mode)

                    # Draw dwell arc
                    draw_dwell_arc(frame, lms[INDEX_TIP].x, lms[INDEX_TIP].y, progress, mode)

            else:
                # Hand left frame
                emergency_cancel()
                ds.pos_history.clear()
                ds.prev_raw      = None
                ds.prev_scroll_y = None
                ds.palm_count    = 0

            # HUD
            mode_colors = {
                "idle":     (80, 200, 120),
                "down":     (80, 180, 255),
                "dragging": (255, 160, 40),
                "scroll":   (180, 120, 255),
                "cancel":   (80, 80, 255),
                "clicked":  (255, 255, 255),
                "dropped":  (255, 255, 255),
                "no hand":  (100, 100, 100),
            }
            col = mode_colors.get(mode, (180, 180, 180))
            cv2.putText(frame, mode.upper(), (12, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, col, 2)
            cv2.putText(frame, f"dwell: {DWELL_MS}ms",
                        (12, FRAME_H - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (140,140,140), 1)
            cv2.putText(frame, "bus:ok" if _bus_connected else "bus:off",
                        (12, FRAME_H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (140,140,140), 1)

            cv2.imshow("Gesture v4 — dwell click — Q to quit", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('+') or key == ord('='):
                DWELL_MS_ref = globals()
                globals()['DWELL_MS'] = min(DWELL_MS + 50, 1500)
                print(f"Dwell: {DWELL_MS}ms")
            elif key == ord('-'):
                globals()['DWELL_MS'] = max(DWELL_MS - 50, 150)
                print(f"Dwell: {DWELL_MS}ms")

    emergency_cancel()
    cap.release()
    cv2.destroyAllWindows()
    print("Stopped.")

if __name__ == "__main__":
    main()
