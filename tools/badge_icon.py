#!/usr/bin/env python3
"""nada launcher icon: an eighth note, because nada means "note/tone".

Same shared rules as the other vanipy apps: numbers-only version strip across
the bottom 24%, picture inside the round-mask safe circle, deterministic
output (pinned Pillow + pinned DejaVu font vendored in tools/fonts/, fail
instead of substituting).
    pip install pillow==12.3.0
"""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PILLOW_PIN = "12.3.0"
import PIL
from PIL import ImageDraw

if PIL.__version__ != PILLOW_PIN:
    sys.exit("Pillow %s required, found %s" % (PILLOW_PIN, PILLOW_PIN and PIL.__version__))

import importlib.util

HELPERS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "badge_common.py")
spec = importlib.util.spec_from_file_location("badge_common", HELPERS)
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)

S = common.S


def note(version):
    BG = (11, 114, 133, 255)      # nada teal (web UI primary #0b7285)
    STRIP = (7, 77, 92, 255)      # darker teal
    WHITE = (250, 250, 247, 255)
    AMBER = (255, 179, 0, 255)
    art, d = common.new_layer()
    # eighth note: tilted head, stem, flag - centered above the strip
    # head: ellipse tilted ~20 degrees, drawn via polygon around an ellipse
    cx, cy, rx, ry, tilt = 0.40, 0.585, 0.095, 0.068, math.radians(-20)
    pts = []
    for i in range(61):
        t = i / 60 * 2 * math.pi
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append(((cx + x * math.cos(tilt) - y * math.sin(tilt)) * S,
                    (cy + x * math.sin(tilt) + y * math.cos(tilt)) * S))
    d.polygon(pts, fill=WHITE)
    # stem: right side of the head, going up
    d.rectangle([(0.475) * S, (0.215) * S, (0.515) * S, (0.585) * S], fill=WHITE)
    # flag: curved swoosh from the top of the stem to the right
    flag = []
    for i in range(41):
        t = i / 40
        x = 0.515 + 0.135 * math.sin(t * math.pi / 2)
        y = 0.215 + 0.19 * (t ** 1.6)
        flag.append((x * S, y * S))
    for i in range(40, -1, -1):
        t = i / 40
        x = 0.515 + 0.135 * math.sin(t * math.pi / 2) - 0.045
        y = 0.215 + 0.19 * (t ** 1.6) - 0.045
        flag.append((x * S, y * S))
    d.polygon(flag, fill=WHITE)
    # two sound-wave arcs to the right of the note, amber
    for rr, wd in ((0.10, 0.016), (0.155, 0.016)):
        box = [((cx + 0.10) - rr) * S, ((cy - 0.16) - rr) * S,
               ((cx + 0.10) + rr) * S, ((cy - 0.16) + rr) * S]
        d.arc(box, start=-55, end=55, fill=AMBER, width=int(wd * S))
    return common.compose(BG, art, version, STRIP, WHITE, rounded=.2)


def main():
    version = common.parse_version(sys.argv)
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    common.write_densities(note(version), os.path.join(root, "android/app/src/main/res"))
    print("wrote nada icons for", version)


if __name__ == "__main__":
    main()
