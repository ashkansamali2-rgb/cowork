#!/usr/bin/env python3
"""
Generate Jarvis extension icons as PNG files.
Pure Python, no external dependencies required.
Run: python3 generate-icons-py.py
"""
import struct
import zlib
import math
import os

def make_png(width, height, pixels_rgba):
    """Create a PNG file from RGBA pixel data (list of rows, each row a list of [R,G,B,A])."""
    def chunk(name, data):
        crc = zlib.crc32(name + data) & 0xffffffff
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', crc)

    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    raw_rows = b''
    for row in pixels_rgba:
        raw_rows += b'\x00'  # filter type: None
        for px in row:
            raw_rows += bytes(px)

    idat_data = zlib.compress(raw_rows, 9)
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', ihdr_data)
        + chunk(b'IDAT', idat_data)
        + chunk(b'IEND', b'')
    )

def lerp(a, b, t):
    return a + (b - a) * t

def generate_icon(size):
    # Colors
    c1 = (124, 58, 237)   # #7C3AED
    c2 = (91, 33, 182)    # #5B21B6
    radius = size * 0.22  # corner radius

    pixels = []
    for y in range(size):
        row = []
        for x in range(size):
            # Rounded rectangle test
            # Find nearest corner zone
            cx_near = max(radius, min(size - radius, x))
            cy_near = max(radius, min(size - radius, y))
            dist = math.sqrt((x - cx_near) ** 2 + (y - cy_near) ** 2)

            if dist <= radius:
                # Gradient from top-left to bottom-right
                t = (x + y) / (2.0 * (size - 1))
                r = int(lerp(c1[0], c2[0], t))
                g = int(lerp(c1[1], c2[1], t))
                b = int(lerp(c1[2], c2[2], t))
                # Anti-alias edge
                alpha = 255
                if dist > radius - 1.0:
                    alpha = int(255 * (radius - dist))
                    alpha = max(0, min(255, alpha))
                row.append([r, g, b, alpha])
            else:
                row.append([0, 0, 0, 0])
        pixels.append(row)

    # Draw white 'J' letter
    sw = max(1, int(size * 0.11))  # stroke width

    def set_pixel(px, py, alpha=255):
        if 0 <= px < size and 0 <= py < size:
            bg = pixels[py][px]
            if bg[3] > 0:  # only draw on the icon background
                pixels[py][px] = [255, 255, 255, alpha]

    def draw_thick(px, py, thickness, alpha=255):
        half = thickness // 2
        for dx in range(-half, half + 1):
            for dy in range(-half, half + 1):
                set_pixel(px + dx, py + dy, alpha)

    # Vertical bar of J (right-center, top 20%–68%)
    bar_x = int(size * 0.55)
    for y in range(int(size * 0.18), int(size * 0.68)):
        draw_thick(bar_x, y, sw)

    # Hook: arc from bottom of vertical bar, curling left
    hook_cx = int(size * 0.42)
    hook_cy = int(size * 0.65)
    hook_r = int(size * 0.155)

    steps = max(60, size * 3)
    for i in range(steps + 1):
        angle = math.pi * (1.0 + i / steps)  # pi to 2pi = bottom half circle going left
        hx = int(hook_cx + hook_r * math.cos(angle))
        hy = int(hook_cy + hook_r * math.sin(angle))
        draw_thick(hx, hy, sw)

    return make_png(size, size, pixels)


icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
os.makedirs(icons_dir, exist_ok=True)

for size in [16, 48, 128]:
    data = generate_icon(size)
    out_path = os.path.join(icons_dir, f'icon{size}.png')
    with open(out_path, 'wb') as f:
        f.write(data)
    print(f'Generated {out_path} ({len(data)} bytes)')

print('All icons generated successfully.')
