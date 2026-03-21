# LED Grid Visualizer

A 32x32 pixel LED grid visualizer that runs in the browser and can drive a physical RGB LED matrix via USB serial.

## What it does

- Displays a 32x32 pixel canvas in the browser, styled like an LED screen
- Runs particle animations (shooting stars, sparkles) in real time
- Streams frames over USB serial to a [Pimoroni Interstate 75](https://shop.pimoroni.com/products/interstate-75) board driving a HUB75 RGB LED matrix
- Uses Web Serial API (Chrome/Edge) — no drivers or native apps needed

## Hardware

- **Pimoroni Interstate 75** (RP2040-based HUB75 driver board)
- **32x32 HUB75 RGB LED matrix panel**
- USB-C cable to connect the board to your computer

## Setup

### 1. Flash the board

1. Download the [Pimoroni MicroPython firmware](https://github.com/pimoroni/pimoroni-pico/releases) (`.uf2` file for Interstate 75)
2. Hold BOOT on the board, plug in USB — it mounts as `RPI-RP2`
3. Drag the `.uf2` file onto the drive

### 2. Upload the firmware

1. Open [Thonny](https://thonny.org) → Tools → Options → Interpreter → MicroPython (Raspberry Pi Pico)
2. Open `interstate75/main.py`
3. File → Save As → Raspberry Pi Pico → save as `main.py`
4. Close Thonny (only one app can use the serial port)

### 3. Run the visualizer

1. Unplug/replug the board so `main.py` starts automatically
2. Open `index.html` in Chrome
3. Click **Connect to Interstate 75** and select the USB serial port
4. The animation plays on both the browser and the physical LED matrix

## Serial Protocol

Fire-and-forget streaming at 1.5 Mbaud:

| Byte(s) | Description |
|---------|-------------|
| `0xFF` | Sync byte (frame start marker) |
| 1024 bytes | RGB332 pixel data (1 byte per pixel, 32x32) |

- RGB332 encoding: 3 bits red, 3 bits green, 2 bits blue per pixel
- Pixel values are capped at `0xFE` so the sync byte `0xFF` is unambiguous
- No ACK — the board resyncs on the next `0xFF` if any data is lost
- The board expands RGB332 → RGB888 directly into the PicoGraphics framebuffer using Viper-compiled blitting (near-C speed)

## Files

```
index.html              Web visualizer + serial streaming
interstate75/main.py    MicroPython firmware for the Interstate 75
```
