"""
Interstate 75 - RGB LED Matrix Driver (direct framebuffer + viper)
Receives 32x32 pixel frames over USB serial from the web visualizer.

Protocol (no ACK — fire and forget):
  - Scan for sync byte 0xFF (pixel values capped at 0xFE by sender)
  - Read 3072 bytes (32*32 pixels * 3 bytes RGB)
  - Blit directly into PicoGraphics framebuffer
  - If data is lost, board resyncs on next 0xFF automatically

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
PIXELS = WIDTH * HEIGHT            # 1024
FRAME_SIZE = PIXELS                # 1024 bytes (RGB332, 1 byte/pixel)
FB_BYTES = PIXELS * 3              # 3072 bytes in framebuffer (RGB888)
SYNC_BYTE = 0xFF

# --- Setup display ---
i75 = Interstate75(display=DISPLAY_INTERSTATE75_32X32)
graphics = i75.display
graphics.set_backlight(1.0)

# Get direct framebuffer access
fb = memoryview(graphics)
FB_SIZE = len(fb)


@micropython.viper
def blit_332_to_rgb(fb_ptr, frame_ptr, n: int):
    """Expand RGB332 (1 byte/pixel) → RGB888 framebuffer. Viper = near-C speed."""
    fb_buf = ptr8(fb_ptr)
    src = ptr8(frame_ptr)
    for i in range(n):
        v = int(src[i])
        # RGB332: RRRGGGBB → expand to 8-bit per channel
        fb_buf[i * 3] = (v >> 5) * 36         # R: 3 bits → 0-252
        fb_buf[i * 3 + 1] = ((v >> 2) & 7) * 36  # G: 3 bits → 0-252
        fb_buf[i * 3 + 2] = (v & 3) * 85      # B: 2 bits → 0-255


@micropython.viper
def blit_332_to_bgr(fb_ptr, frame_ptr, n: int):
    """Expand RGB332 (1 byte/pixel) → BGR888 framebuffer. Viper = near-C speed."""
    fb_buf = ptr8(fb_ptr)
    src = ptr8(frame_ptr)
    for i in range(n):
        v = int(src[i])
        fb_buf[i * 3] = (v & 3) * 85          # B: 2 bits → 0-255
        fb_buf[i * 3 + 1] = ((v >> 2) & 7) * 36  # G: 3 bits → 0-252
        fb_buf[i * 3 + 2] = (v >> 5) * 36     # R: 3 bits → 0-252


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

    # Determine if we need RGB->BGR swap
    graphics.set_pen(graphics.create_pen(255, 0, 0))
    graphics.pixel(0, 0)
    needs_swap = (fb[0] != 255)
    graphics.set_pen(graphics.create_pen(0, 0, 0))
    graphics.clear()

    # Pick the right blit function once
    blit = blit_332_to_bgr if needs_swap else blit_332_to_rgb

    while True:
        # Wait for sync byte
        b = sys.stdin.buffer.read(1)
        if not b or b[0] != SYNC_BYTE:
            continue

        # Read RGB332 frame (1024 bytes instead of 3072)
        pos = 0
        while pos < FRAME_SIZE:
            chunk = sys.stdin.buffer.read(FRAME_SIZE - pos)
            if chunk:
                frame[pos:pos + len(chunk)] = chunk
                pos += len(chunk)

        # Expand RGB332 → RGB888/BGR888 into framebuffer + update
        blit(fb, frame, PIXELS)
        i75.update()


if __name__ == "__main__":
    main()
