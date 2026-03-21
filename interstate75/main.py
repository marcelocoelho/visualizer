"""
Interstate 75 - RGB LED Matrix Driver (optimized)
Receives 32x32 pixel frames over USB serial from the web visualizer.

Protocol:
  - Wait for sync byte 0xFF
  - Read 3072 bytes (32*32 pixels * 3 bytes RGB)
  - Send back ACK byte 0x06 when ready for next frame

Install: Copy this file as main.py to the Interstate 75 via Thonny.
Requires: Pimoroni MicroPython firmware with Interstate 75 support.
"""

import micropython
import sys
import time
from interstate75 import Interstate75, DISPLAY_INTERSTATE75_32X32

# CRITICAL: Disable Ctrl+C (0x03) interrupt on stdin.
# Without this, any frame pixel containing byte 0x03 crashes the program,
# and byte 0x04 triggers a soft reset — causing the board to reboot.
micropython.kbd_intr(-1)

# --- Configuration ---
WIDTH = 32
HEIGHT = 32
FRAME_SIZE = WIDTH * HEIGHT * 3  # 3072 bytes
SYNC_BYTE = 0xFF
ACK_BYTE = 0x06
BRIGHTNESS = 0.5

# --- Setup display ---
i75 = Interstate75(display=DISPLAY_INTERSTATE75_32X32)
graphics = i75.display
graphics.set_backlight(BRIGHTNESS)

# Pre-build a full RGB332 pen lookup table (256 entries)
# This avoids ALL dictionary lookups and create_pen calls during frame draw.
# RGB332: 3 bits R, 3 bits G, 2 bits B — packed into one byte index.
pen_lut = []
for i in range(256):
    r3 = (i >> 5) & 0x07
    g3 = (i >> 2) & 0x07
    b2 = i & 0x03
    pen_lut.append(graphics.create_pen(r3 * 36, g3 * 36, b2 * 85))

# Convert to tuple for faster indexing in viper
pen_lut = tuple(pen_lut)


def show_startup():
    """Show a brief startup pattern to confirm the board is running."""
    graphics.set_pen(graphics.create_pen(0, 0, 0))
    graphics.clear()
    for i in range(WIDTH):
        pen = graphics.create_pen(0, int(i * 8), int((31 - i) * 8))
        graphics.set_pen(pen)
        graphics.line(i, 0, i, HEIGHT - 1)
    i75.update()
    time.sleep(1)
    graphics.set_pen(graphics.create_pen(0, 0, 0))
    graphics.clear()
    i75.update()


def read_exact(n):
    """Read exactly n bytes from stdin, blocking until complete."""
    buf = bytearray(n)
    pos = 0
    while pos < n:
        chunk = sys.stdin.buffer.read(n - pos)
        if chunk:
            buf[pos:pos + len(chunk)] = chunk
            pos += len(chunk)
    return buf


def send_ack():
    """Send ACK byte and flush."""
    sys.stdout.buffer.write(bytes([ACK_BYTE]))
    try:
        sys.stdout.buffer.flush()
    except:
        pass
    try:
        sys.stdout.flush()
    except:
        pass


def draw_frame(frame):
    """Draw frame using RGB332 quantized LUT — no per-pixel dict lookup."""
    idx = 0
    for y in range(32):
        for x in range(32):
            r = frame[idx]
            g = frame[idx + 1]
            b = frame[idx + 2]
            idx += 3
            # Quantize to RGB332: 3 bits R, 3 bits G, 2 bits B
            key = (r & 0xE0) | ((g >> 3) & 0x1C) | (b >> 6)
            graphics.set_pen(pen_lut[key])
            graphics.pixel(x, y)


def show_waiting():
    """Red pixel in corner = waiting for serial data."""
    graphics.set_pen(graphics.create_pen(30, 0, 0))
    graphics.pixel(0, 0)
    i75.update()


def main():
    show_startup()
    show_waiting()

    # Pre-allocate frame buffer to avoid repeated allocation
    frame = bytearray(FRAME_SIZE)

    while True:
        # Wait for sync byte
        b = sys.stdin.buffer.read(1)
        if not b or b[0] != SYNC_BYTE:
            continue

        # Read frame into pre-allocated buffer
        pos = 0
        while pos < FRAME_SIZE:
            chunk = sys.stdin.buffer.read(FRAME_SIZE - pos)
            if chunk:
                frame[pos:pos + len(chunk)] = chunk
                pos += len(chunk)

        # Draw and update
        draw_frame(frame)
        i75.update()

        # ACK — ready for next frame
        send_ack()


if __name__ == "__main__":
    main()
