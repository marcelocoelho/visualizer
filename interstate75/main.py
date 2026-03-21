"""
Interstate 75 - RGB LED Matrix Driver (speed-optimized)
Receives 32x32 pixel frames over USB serial from the web visualizer.

Protocol:
  - Scan for sync byte 0xFF (pixel values capped at 0xFE by sender)
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

# Pre-build RGB565 pen lookup table.
# Quantize to 4 bits per channel (12-bit color = 4096 entries).
# This covers all visible colors with fast index computation.
_pen_lut = []
for _i in range(4096):
    _r = ((_i >> 8) & 0x0F) * 17   # 0-255
    _g = ((_i >> 4) & 0x0F) * 17   # 0-255
    _b = (_i & 0x0F) * 17          # 0-255
    _pen_lut.append(graphics.create_pen(_r, _g, _b))


@micropython.native
def draw_frame(frame, lut):
    """Draw RGB888 frame with 12-bit quantized LUT — native compiled."""
    _set_pen = graphics.set_pen
    _pixel = graphics.pixel
    idx = 0
    for y in range(32):
        for x in range(32):
            # Quantize RGB888 to 12-bit (4 bits per channel) for LUT index
            key = ((frame[idx] & 0xF0) << 4) | (frame[idx + 1] & 0xF0) | (frame[idx + 2] >> 4)
            _set_pen(lut[key])
            _pixel(x, y)
            idx += 3


def show_startup():
    """Gradient pattern to confirm the board is running."""
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


def show_waiting():
    """Red pixel in corner = waiting for serial data."""
    graphics.set_pen(graphics.create_pen(30, 0, 0))
    graphics.pixel(0, 0)
    i75.update()


def main():
    show_startup()
    show_waiting()

    # Pre-allocate frame buffer
    frame = bytearray(FRAME_SIZE)
    lut = _pen_lut

    while True:
        # Wait for sync byte (only 0xFF — pixel data is capped at 0xFE)
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
        draw_frame(frame, lut)
        i75.update()

        # ACK — ready for next frame
        send_ack()


if __name__ == "__main__":
    main()
