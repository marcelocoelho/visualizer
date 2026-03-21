#!/usr/bin/env python3
"""MNIST CNN — Weight Knob Visualizer

Each network weight is drawn as a rotary knob whose needle angle encodes
its current value.  The model trains live in a background thread; knobs
update every few batches so you can watch the network learn.

  Green  = positive weight
  Red    = negative weight
  Grey   = near-zero weight
  Angle  sweeps 270° : minimum value at −135°, maximum at +135°

Requirements:
    pip install torch torchvision pygame
"""

import sys
import math
import threading
import numpy as np
import pygame

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    import torchvision
    import torchvision.transforms as T
except ImportError:
    sys.exit("Install: pip install torch torchvision pygame")


# ── Palette ────────────────────────────────────────────────────────────────────
BG     = ( 14,  14,  22)
PBG    = ( 24,  24,  38)
PBORD  = ( 48,  48,  70)
POS    = ( 72, 200, 120)   # green  — positive weight
NEG    = (210,  72,  72)   # red    — negative weight
ZERO   = ( 90,  90, 112)   # grey   — near-zero
WHITE  = (230, 230, 245)
DIM    = ( 80,  80, 100)
ACCENT = ( 90, 170, 255)


# ── Model ──────────────────────────────────────────────────────────────────────
class CNN(nn.Module):
    """Small 2-conv CNN for MNIST (28×28 greyscale → 10 classes)."""

    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(1,  8, 3, padding=1)   # 8×1×3×3   =    72 weights
        self.conv2 = nn.Conv2d(8, 16, 3, padding=1)   # 16×8×3×3  = 1 152 weights
        self.pool  = nn.MaxPool2d(2)
        self.fc1   = nn.Linear(16 * 7 * 7, 64)        # 784×64    = 50 176 weights
        self.fc2   = nn.Linear(64, 10)                 # 64×10     =   640 weights

    def forward(self, x):
        x = self.pool(torch.relu(self.conv1(x)))
        x = self.pool(torch.relu(self.conv2(x)))
        return self.fc2(torch.relu(self.fc1(x.flatten(1))))


# ── Shared state (training thread ↔ render thread) ─────────────────────────────
_lock  = threading.Lock()
_snaps = {}          # key → flat numpy array (copy)
_stats = dict(epoch=0, batch=0, loss=float("nan"),
              acc=0.0, done=False, n_batches=1)


def _snapshot(model):
    with _lock:
        for k, p in model.named_parameters():
            _snaps[k] = p.detach().cpu().numpy().ravel().copy()


# ── Training thread ────────────────────────────────────────────────────────────
def train_loop():
    dev   = "cuda" if torch.cuda.is_available() else "cpu"
    model = CNN().to(dev)
    opt   = optim.Adam(model.parameters(), lr=1e-3)
    crit  = nn.CrossEntropyLoss()
    tf    = T.Compose([T.ToTensor(), T.Normalize((0.1307,), (0.3081,))])
    ds    = torchvision.datasets.MNIST(
                "./data", train=True, download=True, transform=tf)
    dl    = torch.utils.data.DataLoader(
                ds, batch_size=256, shuffle=True, num_workers=0)

    _snapshot(model)
    with _lock:
        _stats["n_batches"] = len(dl)

    for epoch in range(20):
        ok = total = 0
        for b, (X, y) in enumerate(dl):
            X, y  = X.to(dev), y.to(dev)
            opt.zero_grad()
            out   = model(X)
            loss  = crit(out, y)
            loss.backward()
            opt.step()
            ok    += (out.argmax(1) == y).sum().item()
            total += len(y)
            if b % 4 == 0:
                _snapshot(model)
                with _lock:
                    _stats.update(epoch=epoch + 1, batch=b,
                                  loss=loss.item(), acc=ok / total)

    with _lock:
        _stats["done"] = True


# ── Knob geometry & drawing ────────────────────────────────────────────────────
KNOB_R = 11   # knob body radius (pixels)
STEP   = 26   # grid pitch (centre-to-centre)


def _weight_to_angle(v, lo, hi):
    """Map weight value to indicator angle (radians).
    Sweeps 270°: lo → −135° (bottom-left), hi → +135° (bottom-right)."""
    if hi <= lo:
        return 0.0
    t = max(0.0, min(1.0, (v - lo) / (hi - lo)))
    return math.radians(-135.0 + t * 270.0)


def draw_knob(surf, cx, cy, v, lo, hi):
    col = POS if v > 0.04 else (NEG if v < -0.04 else ZERO)
    a   = _weight_to_angle(v, lo, hi)
    ix  = cx + int((KNOB_R - 3) * math.sin(a))
    iy  = cy - int((KNOB_R - 3) * math.cos(a))

    pygame.draw.circle(surf, (30, 30, 46), (cx, cy), KNOB_R)        # body
    pygame.draw.circle(surf, (65, 65, 88), (cx, cy), KNOB_R, 1)    # rim
    pygame.draw.line  (surf, col, (cx, cy), (ix, iy), 2)            # needle
    pygame.draw.circle(surf, col, (ix, iy), 2)                      # needle tip


# ── Panel definitions ──────────────────────────────────────────────────────────
# Each tuple: (title, subtitle, weight_key, sampler_fn, n_cols)
# sampler_fn receives the flat weight array and returns the subset to display.

def _all(w):  return w
def _n(n):    return lambda w: w[:n]
def _fc2(w):  return w.reshape(10, 64)[:, :8].ravel()  # 10 outputs × 8 inputs = 80

PANELS = [
    ("Conv 1",
     "8 filters \u00d7 3\u00d73  \u2014  all 72 weights",
     "conv1.weight", _all, 9),

    ("Conv 2",
     "16 filters \u00d7 3\u00d73  \u2014  first 72 of 1\u202f152",
     "conv2.weight", _n(72), 9),

    ("FC 1",
     "784\u219264  \u2014  first 64 of 50\u202f176",
     "fc1.weight", _n(64), 8),

    ("FC 2",
     "10 outputs \u00d7 first 8 inputs  (80 of 640)",
     "fc2.weight", _fc2, 10),
]


# ── Main render loop ───────────────────────────────────────────────────────────
def main():
    pygame.init()
    font_h = pygame.font.SysFont("monospace", 15, bold=True)
    font_m = pygame.font.SysFont("monospace", 12)
    font_s = pygame.font.SysFont("monospace", 10)

    PANEL_W = 330
    PANEL_H = 320
    MARGIN  = 18
    HEADER  = 92     # pixels reserved for title / status / legend

    SW = MARGIN + len(PANELS) * (PANEL_W + MARGIN)
    SH = HEADER + PANEL_H + MARGIN + 28   # +28 for footer bar

    screen = pygame.display.set_mode((SW, SH))
    pygame.display.set_caption("MNIST CNN \u2014 Weight Knob Visualizer")
    clock  = pygame.time.Clock()

    threading.Thread(target=train_loop, daemon=True).start()

    while True:
        # ── events ────────────────────────────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); return
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                pygame.quit(); return

        screen.fill(BG)

        # ── read shared state ──────────────────────────────────────────────────
        with _lock:
            s     = dict(_stats)
            snaps = {k: v.copy() for k, v in _snaps.items()}

        # ── header ─────────────────────────────────────────────────────────────
        screen.blit(
            font_h.render("MNIST CNN  \u2014  Weight Knob Visualizer", True, ACCENT),
            (MARGIN, 10))

        if s["epoch"] == 0:
            status = "Downloading MNIST and initialising\u2026"
        elif s["done"]:
            status = (f"Training complete!  "
                      f"acc {s['acc']:.1%}   loss {s['loss']:.4f}")
        else:
            status = (f"Epoch {s['epoch']:2d}/20  "
                      f"batch {s['batch']:3d}/{s['n_batches']}  "
                      f"loss {s['loss']:.4f}  "
                      f"acc {s['acc']:.1%}")

        screen.blit(font_m.render(status, True, WHITE), (MARGIN, 34))

        # legend
        lx = MARGIN
        for txt, col in [("\u25cf positive", POS),
                         ("   \u25cf negative", NEG),
                         ("   \u25cf ~zero", ZERO)]:
            surf = font_s.render(txt, True, col)
            screen.blit(surf, (lx, 60))
            lx += surf.get_width()
        screen.blit(
            font_s.render(
                "       needle angle = weight value within layer's [min, max]",
                True, DIM),
            (lx, 60))

        # ── panels ─────────────────────────────────────────────────────────────
        for pi, (title, sub, key, sampler, n_cols) in enumerate(PANELS):
            px = MARGIN + pi * (PANEL_W + MARGIN)
            py = HEADER

            pygame.draw.rect(screen, PBG,   (px, py, PANEL_W, PANEL_H), border_radius=8)
            pygame.draw.rect(screen, PBORD, (px, py, PANEL_W, PANEL_H), 1, border_radius=8)

            screen.blit(font_h.render(title, True, ACCENT), (px + 12, py + 10))
            screen.blit(font_s.render(sub,   True, DIM),    (px + 12, py + 30))

            if key not in snaps:
                screen.blit(font_m.render("waiting\u2026", True, DIM),
                            (px + PANEL_W // 2 - 30, py + PANEL_H // 2))
                continue

            w      = sampler(snaps[key])
            lo, hi = float(w.min()), float(w.max())
            n      = len(w)
            n_rows = math.ceil(n / n_cols)

            # centre the knob grid inside the panel
            grid_w = n_cols * STEP
            grid_h = n_rows * STEP
            ox = px + (PANEL_W - grid_w) // 2 + KNOB_R
            oy = py + 52 + KNOB_R

            for idx, val in enumerate(w):
                r = idx // n_cols
                c = idx  % n_cols
                draw_knob(screen,
                          ox + c * STEP,
                          oy + r * STEP,
                          float(val), lo, hi)

            # bottom-left: weight count
            screen.blit(
                font_s.render(
                    f"showing {n} of {len(snaps[key]):,} weights",
                    True, DIM),
                (px + 12, py + PANEL_H - 20))

            # bottom-right: value range
            range_txt = f"[{lo:+.2f} \u2026 {hi:+.2f}]"
            rs = font_s.render(range_txt, True, DIM)
            screen.blit(rs, (px + PANEL_W - rs.get_width() - 12, py + PANEL_H - 20))

        # ── footer ─────────────────────────────────────────────────────────────
        screen.blit(
            font_s.render(
                "ESC to quit  \u00b7  knobs refresh every 4 batches  \u00b7  "
                "needle points up = mid-range, clockwise = larger positive",
                True, DIM),
            (MARGIN, HEADER + PANEL_H + MARGIN + 4))

        pygame.display.flip()
        clock.tick(30)


if __name__ == "__main__":
    main()
