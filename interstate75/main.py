"""
Interstate 75 - WebUSB LED Matrix Driver
Receives 32x32 RGB888 frames over a raw USB bulk endpoint from the web visualizer.

Protocol (identical to CDC version — no changes needed on the browser side):
  - Sync byte 0xFF followed by 3072 bytes of RGB888 pixel data
  - Fire-and-forget: board resyncs on the next 0xFF if data is lost

Why WebUSB over CDC serial?
  - Bypasses the OS CDC serial driver — no baud-rate fiction, lower latency
  - One transferOut() call in the browser sends all 3073 bytes as pipelined
    64-byte USB full-speed packets, avoiding MicroPython's per-packet stdin loop
  - Effective throughput ~900 KB/s vs ~150-200 KB/s with CDC at 1.5 Mbaud

Requirements:
  - Pimoroni MicroPython firmware v1.23+ (machine.USBDevice API)
  - Chrome or Edge (WebUSB is not supported in Firefox/Safari)

IMPORTANT — Flashing & re-flashing:
  This firmware disables the CDC serial REPL (BUILTIN_NONE).
  Thonny can no longer connect over USB once this is running.
  To re-flash or edit files:
    1. Hold BOOT button while plugging in USB
    2. Board mounts as RPI-RP2 mass storage
    3. Copy new main.py via Thonny in mass-storage mode, or drag a new .uf2

USB identifiers:
  VID 0x2E8A  (Raspberry Pi — permitted on RP2040 hardware)
  PID 0x000A  (custom, unused by any official Pimoroni product)

The original CDC serial firmware is in main_cdc.py for reference/fallback.
"""

import machine
import micropython
import struct
import time
from interstate75 import Interstate75, DISPLAY_INTERSTATE75_32X32

micropython.kbd_intr(-1)   # disable Ctrl+C interrupt

# ── Display ────────────────────────────────────────────────────────────────
WIDTH      = 32
HEIGHT     = 32
PIXELS     = WIDTH * HEIGHT   # 1024
FRAME_SIZE = PIXELS * 3       # 3072 bytes RGB888
SYNC_BYTE  = 0xFF

i75      = Interstate75(display=DISPLAY_INTERSTATE75_32X32)
graphics = i75.display
graphics.set_backlight(1.0)
fb = memoryview(graphics)


@micropython.viper
def blit_rgb_to_bgr(fb_ptr, frame_ptr, n: int):
    """Copy frame into display framebuffer swapping R and B channels."""
    fb_buf = ptr8(fb_ptr)
    src    = ptr8(frame_ptr)
    for i in range(0, n, 3):
        fb_buf[i]     = src[i + 2]   # B
        fb_buf[i + 1] = src[i + 1]   # G
        fb_buf[i + 2] = src[i]       # R


@micropython.viper
def blit_direct(fb_ptr, frame_ptr, n: int):
    """Copy frame directly into display framebuffer."""
    fb_buf = ptr8(fb_ptr)
    src    = ptr8(frame_ptr)
    for i in range(n):
        fb_buf[i] = src[i]


def show_startup():
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


# Detect whether this display wants RGB or BGR byte order
graphics.set_pen(graphics.create_pen(255, 0, 0))
graphics.pixel(0, 0)
needs_swap = (fb[0] != 255)
graphics.set_pen(graphics.create_pen(0, 0, 0))
graphics.clear()
blit = blit_rgb_to_bgr if needs_swap else blit_direct


# ── USB descriptor constants ───────────────────────────────────────────────
EP_OUT         = 0x01   # Bulk OUT endpoint address (host→device)
VENDOR_CODE    = 0x01   # Arbitrary code Chrome uses to request the WebUSB URL
MS_VENDOR_CODE = 0x02   # Arbitrary code Windows uses to request MS OS 2.0 descriptors

# Landing page shown in Chrome's "device detected" notification
# Scheme 0x00 = http://,  0x01 = https://
LANDING_SCHEME = 0x00
LANDING_URL    = b"localhost:8080/index.html"

# WebUSB Platform Capability UUID — fixed value defined by the WebUSB spec
# {3408b638-09a9-47a0-8bfd-a0768815b665}
_WEBUSB_UUID = b'\x38\xb6\x08\x34\xa9\x09\xa0\x47\x8b\xfd\xa0\x76\x88\x15\xb6\x65'

# MS OS 2.0 Platform Capability UUID — fixed value defined by Microsoft
# {D8DD60DF-4589-4CC7-9CD2-659D9E648A9F}
# Including this makes Windows auto-install WinUSB — no Zadig tool needed
_MSOS20_UUID  = b'\xdf\x60\xdd\xd8\x89\x45\xc7\x4c\x9c\xd2\x65\x9d\x9e\x64\x8a\x9f'


# ── USB Descriptors ────────────────────────────────────────────────────────

# Device descriptor
# bcdUSB 2.10 is required — hosts only request the BOS descriptor for USB 2.1+ devices
DESC_DEV = bytes([
    18,                  # bLength
    0x01,                # bDescriptorType: Device
    0x10, 0x02,          # bcdUSB 2.10
    0xFF, 0x00, 0x00,    # bDeviceClass/SubClass/Protocol: Vendor Specific
    64,                  # bMaxPacketSize0
    0x8A, 0x2E,          # idVendor  0x2E8A (Raspberry Pi)
    0x0A, 0x00,          # idProduct 0x000A (custom LED matrix)
    0x00, 0x01,          # bcdDevice 1.0
    1, 2, 0,             # iManufacturer, iProduct, iSerialNumber
    1,                   # bNumConfigurations
])

# Configuration descriptor: one interface, one bulk-OUT endpoint
# Total = 9 (config) + 9 (interface) + 7 (endpoint) = 25 bytes
DESC_CFG = bytes([
    # Configuration descriptor
    9, 0x02, 25, 0,      # bLength, bDescriptorType, wTotalLength
    1, 1, 0,             # bNumInterfaces, bConfigurationValue, iConfiguration
    0x80, 250,           # bmAttributes (bus-powered), bMaxPower (500 mA)
    # Interface descriptor
    9, 0x04,             # bLength, bDescriptorType
    0, 0,                # bInterfaceNumber, bAlternateSetting
    1,                   # bNumEndpoints
    0xFF, 0x00, 0x00,    # bInterfaceClass/SubClass/Protocol: Vendor Specific
    0,                   # iInterface
    # Bulk OUT endpoint (EP1 OUT)
    7, 0x05,             # bLength, bDescriptorType
    EP_OUT,              # bEndpointAddress
    0x02,                # bmAttributes: Bulk
    64, 0,               # wMaxPacketSize: 64 bytes (USB Full Speed max)
    0,                   # bInterval (unused for bulk)
])

# WebUSB Platform Capability Descriptor (24 bytes)
# Signals to Chrome that this device supports WebUSB and provides a landing URL
_WEBUSB_CAP = (
    bytes([24, 0x10, 0x05, 0x00])   # bLength, bDescriptorType, bDevCapabilityType, bReserved
    + _WEBUSB_UUID
    + struct.pack('<HBB',
        0x0100,           # bcdVersion 1.0
        VENDOR_CODE,      # bVendorCode: Chrome will send a vendor request with this code to get the URL
        1,                # iLandingPage: index 1 means "return URL descriptor index 1"
    )
)

# MS OS 2.0 Descriptor Set total = 10 (header) + 20 (compat ID feature) = 30 bytes
_MSOS20_SET_LEN = 30

# MS OS 2.0 Platform Capability Descriptor (28 bytes)
# Signals to Windows 8.1+ to automatically load WinUSB.sys — no manual driver install
_MSOS20_CAP = (
    bytes([28, 0x10, 0x05, 0x00])   # bLength, bDescriptorType, bDevCapabilityType, bReserved
    + _MSOS20_UUID
    + struct.pack('<IHBB',
        0x06030000,       # dwWindowsVersion: Windows 8.1 minimum
        _MSOS20_SET_LEN,  # wMSOSDescriptorSetTotalLength
        MS_VENDOR_CODE,   # bMS_VendorCode: Windows will use this code to request the descriptor set
        0,                # bAltEnumCode
    )
)

# BOS (Binary Object Store) descriptor — container for the two platform capabilities above
# Total = 5 (header) + 24 (WebUSB cap) + 28 (MS OS 2.0 cap) = 57 bytes
_BOS_TOTAL = 5 + len(_WEBUSB_CAP) + len(_MSOS20_CAP)
DESC_BOS = (
    struct.pack('<BBHB', 5, 0x0F, _BOS_TOTAL, 2)
    + _WEBUSB_CAP
    + _MSOS20_CAP
)

# WebUSB URL descriptor — returned when Chrome requests our landing page
DESC_URL = bytes([len(LANDING_URL) + 3, 0x03, LANDING_SCHEME]) + LANDING_URL

# MS OS 2.0 Descriptor Set — returned when Windows requests WinUSB binding info
# Header (10 bytes) describes the set; Compatible ID feature (20 bytes) names the driver
DESC_MSOS20 = (
    struct.pack('<HHIH',
        10,               # wLength
        0x0000,           # wDescriptorType: Set Header Descriptor
        0x06030000,       # dwWindowsVersion: Windows 8.1
        _MSOS20_SET_LEN,  # wTotalLength
    )
    + struct.pack('<HH', 20, 0x0003)   # wLength, wDescriptorType: Feature Compatible ID
    + b'WINUSB\x00\x00'               # CompatibleID: instructs Windows to use WinUSB.sys
    + b'\x00' * 8                     # SubCompatibleID: unused
)

# String descriptors (referenced by index in DESC_DEV)
DESC_STRS = [
    b'\x09\x04',           # index 0: language (English US)
    b'Raspberry Pi',       # index 1: iManufacturer
    b'LED Matrix WebUSB',  # index 2: iProduct
]


# ── USB receive state machine ──────────────────────────────────────────────
frame    = bytearray(FRAME_SIZE)   # accumulates one full frame
rx_buf   = bytearray(64)           # receive buffer — one USB packet at a time
rx_state = 0   # 0 = waiting for sync byte 0xFF, 1 = receiving pixel data
rx_pos   = 0   # next write position inside frame[]

usb_dev = machine.USBDevice()


def control_xfer_cb(stage, request):
    """
    Handle USB control requests not covered by MicroPython's built-in stack.
    stage=1 SETUP, stage=2 DATA, stage=3 ACK.
    Return a bytes-like buffer to respond with data, True to ACK with no data,
    or False to STALL (reject) the request.
    """
    if stage != 1:
        return True   # ACK DATA and ACK stages without action

    bmRequestType = request[0]
    bRequest      = request[1]
    wValue        = request[2] | (request[3] << 8)
    wIndex        = request[4] | (request[5] << 8)

    # Standard GET_DESCRIPTOR request — host asks for the BOS descriptor
    if bmRequestType == 0x80 and bRequest == 0x06:
        if (wValue >> 8) == 0x0F:    # descriptor type BOS
            return DESC_BOS

    # WebUSB vendor request — Chrome asks for our landing page URL descriptor
    if bmRequestType == 0xC0 and bRequest == VENDOR_CODE:
        if wIndex == 0x0002:         # GET_URL
            return DESC_URL

    # MS OS 2.0 vendor request — Windows asks for the WinUSB compat-ID descriptor set
    if bmRequestType == 0xC0 and bRequest == MS_VENDOR_CODE:
        if wIndex == 0x0007:         # MS_OS_20_DESCRIPTOR_INDEX
            return DESC_MSOS20

    return False   # STALL anything unrecognised


def xfer_cb(ep_addr, result, xferred):
    """
    Called after each completed USB bulk transfer.
    Feed received bytes through the sync→accumulate→blit state machine,
    then immediately re-arm the endpoint for the next packet.
    """
    global rx_state, rx_pos

    if ep_addr == EP_OUT and result == 0 and xferred > 0:
        i = 0
        while i < xferred:
            if rx_state == 0:
                # Scanning for the 0xFF frame-start sync byte
                if rx_buf[i] == SYNC_BYTE:
                    rx_state = 1
                    rx_pos   = 0
                i += 1
            else:
                # Accumulating pixel bytes until we have a full frame
                space = min(FRAME_SIZE - rx_pos, xferred - i)
                frame[rx_pos:rx_pos + space] = rx_buf[i:i + space]
                rx_pos += space
                i      += space
                if rx_pos >= FRAME_SIZE:
                    blit(fb, frame, FRAME_SIZE)
                    i75.update()
                    rx_state = 0

    # Re-queue the receive buffer so the endpoint stays armed
    usb_dev.submit_xfer(EP_OUT, rx_buf)


def open_itf_cb(interface_desc):
    """Called when the USB host selects our configuration. Arm EP1 OUT."""
    usb_dev.submit_xfer(EP_OUT, rx_buf)


# ── Start ──────────────────────────────────────────────────────────────────

show_startup()

# Swap out the built-in CDC serial stack for our custom WebUSB device
usb_dev.builtin_driver = machine.USBDevice.BUILTIN_NONE
usb_dev.config(
    desc_dev        = DESC_DEV,
    desc_cfg        = DESC_CFG,
    desc_strs       = DESC_STRS,
    open_itf_cb     = open_itf_cb,
    xfer_cb         = xfer_cb,
    control_xfer_cb = control_xfer_cb,
)
usb_dev.active(True)

# Solid blue pixel = waiting for WebUSB connection
graphics.set_pen(graphics.create_pen(0, 0, 60))
graphics.pixel(0, 0)
i75.update()

# All work happens in the USB callbacks.
# machine.idle() sleeps the CPU until the next interrupt (USB packet, timer, etc.)
while True:
    machine.idle()
