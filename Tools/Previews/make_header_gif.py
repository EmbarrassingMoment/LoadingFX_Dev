"""Rebuilds Docs/images/spinners.gif from a Showcase recording, with the tiles rearranged into two rows.

    python make_header_gif.py <capture.mkv> <out.gif> [per_row]

Record with: record_showcase.ps1 -ExecCmds "LFXProto.Showcase 108" -Out <capture.mkv> -Seconds 10
(1600x900, every material with its caption under the tile). The Showcase wraps its tiles to the window, which
left two tiles alone on a third row once there were 24. Each item (tile and caption) is cut out of the frame
where the window put it and placed again in rows of per_row items, centered, in the Showcase's order.
90 frames, 70 ms each, like the 1.0 header. Needs ffmpeg / ffprobe on PATH, numpy and Pillow.
"""
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image

FRAME_MS = 70
FRAMES = 90
GAP_X, GAP_Y, MARGIN = 18, 22, 6


def read_frames(path):
    w, h = map(int, subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
         path], text=True).strip().split(",")[:2])
    times = np.array([float(l.split(",")[0]) for l in subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time", "-of", "csv=p=0",
         path], text=True).splitlines() if l.strip()])
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)
    return frames, times - times[0]


def runs(flags):
    out, start = [], None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(flags)))
    return out


def find_items(frame):
    mask = frame.max(axis=2) > 8
    mask[:, :4] = mask[:, -4:] = False      # window border
    mask[:4, :] = mask[-4:, :] = False
    bands = runs(mask.any(axis=1))
    # A row group is a band of tiles followed by its band of captions: merge bands closer than 12 px.
    groups = []
    for y0, y1 in bands:
        if groups and y0 - groups[-1][1] < 12:
            groups[-1] = (groups[-1][0], y1)
        else:
            groups.append((y0, y1))
    items = []
    for y0, y1 in groups:
        for x0, x1 in runs(mask[y0:y1].any(axis=0)):
            items.append((x0, y0, x1, y1))
    return items


def main():
    src, out = sys.argv[1], sys.argv[2]
    per_row = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    frames, times = read_frames(src)
    ref = frames[len(frames) // 2]
    items = find_items(ref)
    print(f"{len(items)} items")
    rows = [items[i:i + per_row] for i in range(0, len(items), per_row)]
    row_w = [sum(x1 - x0 for x0, _, x1, _ in r) + GAP_X * (len(r) - 1) for r in rows]
    row_h = [max(y1 - y0 for _, y0, _, y1 in r) for r in rows]
    W = max(row_w) + 2 * MARGIN
    H = sum(row_h) + GAP_Y * (len(rows) - 1) + 2 * MARGIN
    start = times[-1] / 2 - FRAMES * FRAME_MS / 2000
    out_frames = []
    for k in range(FRAMES):
        fi = int(np.argmin(np.abs(times - (start + k * FRAME_MS / 1000))))
        fr = frames[fi]
        canvas = np.zeros((H, W, 3), np.uint8)
        y = MARGIN
        for r, rw, rh in zip(rows, row_w, row_h):
            x = MARGIN + (W - 2 * MARGIN - rw) // 2
            for x0, y0, x1, y1 in r:
                canvas[y:y + (y1 - y0), x:x + (x1 - x0)] = fr[y0:y1, x0:x1]
                x += x1 - x0 + GAP_X
            y += rh + GAP_Y
        out_frames.append(Image.fromarray(canvas))
    # ffmpeg writes only the rectangle that changed in each frame, on one palette for the whole clip.
    tmp = out + ".frames"
    os.makedirs(tmp, exist_ok=True)
    for i, f in enumerate(out_frames):
        f.save(os.path.join(tmp, f"{i:03d}.png"))
    rate = f"1000/{FRAME_MS}"
    pattern = os.path.join(tmp, "%03d.png")
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-framerate", rate, "-i", pattern, "-vf",
                           "palettegen=max_colors=96:stats_mode=diff", os.path.join(tmp, "palette.png")])
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-framerate", rate, "-i", pattern, "-i",
                           os.path.join(tmp, "palette.png"), "-lavfi",
                           "paletteuse=dither=none:diff_mode=rectangle", "-loop", "0", out])
    shutil.rmtree(tmp)
    print(f"{W}x{H}, {FRAMES} frames")


if __name__ == "__main__":
    main()
