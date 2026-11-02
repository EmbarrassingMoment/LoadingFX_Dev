"""Cuts one seamless looping GIF per material out of a lossless Showcase recording (README previews).

Usage: python make_previews.py <capture.mkv> <out_dir> spinners|bars
  spinners: record_showcase.ps1 -ExecCmds "LFXProto.Showcase 192 spinners" (160 px tiles at 1600x900)
  bars:     record_showcase.ps1 -ExecCmds "LFXProto.Showcase 384 bars" -Seconds 8 (320x80 tiles)

Each material loops over its period with the default parameters (taken from the builder scripts: change the
tables below when a default Speed or Count changes), sampled at OUT_FPS by the capture timestamps and halved
in size. The loop start is the capture frame whose partner one period later matches it best, which absorbs
the capture's timing jitter at the seam. Needs ffmpeg / ffprobe on PATH, numpy and Pillow.
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image

OUT_FPS = 25          # 40 ms per GIF frame (GIF delays are in 1/100 s)
LEVELS = 64           # palette steps from the tile background to white

SPINNERS = [
    # name, period in seconds, extra clockwise turns per period (rotated back over the loop)
    ("M_LoadingDotRing", 1 / 0.64, 0.0),
    ("M_LoadingDotGrid", 1 / 0.8, 0.0),
    ("M_LoadingBoxes", 1.0, 0.0),
    ("M_LoadingSpokes", 1.0, 0.0),
    # One stretch cycle (1 / StretchSpeed) advances the arc by Speed / StretchSpeed + (ArcMax - ArcMin) = 1.02 turns.
    ("M_LoadingArc", 1 / 0.75, 0.02),
    ("M_LoadingComet", 1 / 0.5, 0.0),
    ("M_LoadingDotRow", 1 / 1.1, 0.0),
    # Each ring is symmetric under a half turn: outer 0.7 rev/s, inner -0.91 rev/s -> 10 and 13 half turns in 650/91 s.
    ("M_LoadingDualArc", 650 / 91, 0.0),
    ("M_LoadingSegments", 1 / 0.45, 0.0),
    ("M_LoadingTimer", 1 / 0.5, 0.0),
    ("M_LoadingHourglass", 1 / 0.35, 0.0),
    ("M_LoadingBounce", 1 / 0.9, 0.0),
    ("M_LoadingRipple", 1 / (0.5 * 3), 0.0),
    ("M_LoadingEqualizer", 1.0, 0.0),
    # Three droplets turn at 0.25 rev/s (a third of a turn in 4/3 s) and spread at 0.5 Hz (2 s): 4 s.
    ("M_LoadingGooey", 4.0, 0.0),
    ("M_LoadingMorph", 1 / 0.5, 0.0),
    ("M_LoadingLine", 1 / 0.6, 0.0),
    ("M_LoadingChase", 1 / 0.55, 0.0),
]
BARS = [
    ("M_LoadingBarSlide", 1 / 0.6, 0.0),
    ("M_LoadingBarStripes", 1.0, 0.0),
    ("M_LoadingBarFill", 1 / 0.5, 0.0),   # the sheen does not show on white: expect a still
]


def probe_size(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height", "-of", "csv=p=0", path], text=True)
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


def probe_times(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "frame=pts_time", "-of", "csv=p=0", path], text=True)
    return np.array([float(l.split(",")[0]) for l in out.splitlines() if l.strip()])


def runs(idx):
    result = []
    start = prev = idx[0]
    for i in idx[1:]:
        if i != prev + 1:
            result.append((start, prev))
            start = i
        prev = i
    result.append((start, prev))
    return result


def find_tiles(frame):
    """Tile rectangles (x, y, w, h) in reading order: the dark backings on the black background."""
    mask = frame.max(axis=2) > 8
    tiles = []
    for y0, y1 in runs(np.where(mask.any(axis=1))[0]):
        if y1 - y0 < 30:      # captions and the window edge
            continue
        for x0, x1 in runs(np.where(mask[y0:y1 + 1].any(axis=0))[0]):
            tiles.append((x0, y0, x1 - x0 + 1, y1 - y0 + 1))
    return tiles


def main():
    capture, out_dir, kind = sys.argv[1], sys.argv[2], sys.argv[3]
    materials = SPINNERS if kind == "spinners" else BARS
    w, h = probe_size(capture)
    times = probe_times(capture)
    # passthrough: one raw frame per captured frame, so the frames line up with their timestamps.
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", capture, "-fps_mode", "passthrough", "-f", "rawvideo",
                             "-pix_fmt", "rgb24", "-"],
                            stdout=subprocess.PIPE)
    frames = []
    tiles = None
    while True:
        buf = proc.stdout.read(w * h * 3)
        if len(buf) < w * h * 3:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        if tiles is None:
            tiles = find_tiles(frame)
            assert len(tiles) == len(materials), f"found {len(tiles)} tiles for {len(materials)} materials: {tiles}"
            background = frame[tiles[0][1] + 2, tiles[0][0] + 2].astype(np.float32)
        frames.append([frame[y:y + th, x:x + tw].copy() for x, y, tw, th in tiles])
    proc.wait()
    assert len(frames) == len(times), f"{len(frames)} frames but {len(times)} timestamps"
    print(f"{len(frames)} frames over {times[-1] - times[0]:.2f} s, {len(tiles)} tiles of {tiles[0][2]}x{tiles[0][3]}, "
          f"background {background}")

    # One palette for every GIF: the tile background blended toward white (every material is white on it).
    steps = np.linspace(0.0, 1.0, LEVELS)[:, None]
    palette_colors = np.round(background[None, :] + steps * (255.0 - background[None, :])).astype(np.uint8)
    palette_image = Image.new("P", (1, 1))
    palette_image.putpalette(palette_colors.flatten().tolist() + [0] * (768 - LEVELS * 3))

    def nearest(t):
        return int(np.argmin(np.abs(times - t)))

    def diff(a, b):
        return float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean())

    for index, (name, period, extra_turns) in enumerate(materials):
        tile = [f[index] for f in frames]
        # Loop start: the frame whose partner one period later matches best (after undoing the extra turn).
        best = None
        for i in range(len(frames)):
            j = nearest(times[i] + period)
            # The game presents at a steady 60 Hz, so a partner is at most half a frame off the period.
            if times[i] + period > times[-1] or abs(times[j] - times[i] - period) > 0.009:
                continue
            partner = tile[j]
            if extra_turns:
                partner = np.asarray(Image.fromarray(partner).rotate(extra_turns * 360.0, resample=Image.BICUBIC,
                                                                     fillcolor=tuple(int(c) for c in background)))
            d = diff(tile[i], partner)
            if best is None or d < best[0]:
                best = (d, i)
        seam, start = best
        count = max(1, round(period * OUT_FPS))
        out_frames = []
        for k in range(count):
            image = Image.fromarray(tile[nearest(times[start] + k * period / count)])
            if extra_turns:
                image = image.rotate(extra_turns * 360.0 * k / count, resample=Image.BICUBIC,
                                     fillcolor=tuple(int(c) for c in background))
            out_frames.append(image.reduce(2))
        step = np.mean([diff(np.asarray(a), np.asarray(b)) for a, b in zip(out_frames, out_frames[1:])]) if count > 1 else 0.0
        wrap = diff(np.asarray(out_frames[-1]), np.asarray(out_frames[0]))
        # A still material (the fill bar on white) becomes a single frame.
        if step < 0.05:
            out_frames = out_frames[:1]
        paletted = [f.quantize(palette=palette_image, dither=Image.Dither.NONE) for f in out_frames]
        path = f"{out_dir}/{name}.gif"
        paletted[0].save(path, save_all=True, append_images=paletted[1:], duration=int(1000 / OUT_FPS), loop=0,
                         optimize=False, disposal=1)
        print(f"{name:22s} period {period:6.3f} s  frames {len(out_frames):3d}  start {times[start]:6.3f} s  "
              f"seam {seam:5.2f}  mean step {step:5.2f}  wrap step {wrap:5.2f}  {os.path.getsize(path) / 1024:6.1f} KB")


if __name__ == "__main__":
    main()
