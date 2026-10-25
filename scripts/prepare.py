"""Prepare the static inputs for build.py: font subsets, glyph metrics, icons and screenshot crops.

Run locally when fonts, icons or screenshots change. Needs fonttools, brotli and pillow.
build.py itself uses the standard library only, so the hourly Action installs nothing.

    python scripts/prepare.py --fonts DIR --icons DIR --screens DIR --signature EMSAllure.svg
"""

import argparse
import json
import re
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "src"

# Latin for all copy, Cyrillic for the inkey demo, plus the few symbols the cards use
UNICODES = list(range(0x20, 0x7F)) + [0xA0, 0xB7, 0x2192, 0x2197, 0x2026] + list(range(0x410, 0x450)) + [0x451]
WEIGHTS = [400, 500, 600, 700, 800]

# (output name, source file without theme suffix, crop box as fractions, output width)
SCREENS = [
    ("voice-home", "voice-chat/voice-chat-01-home", (0, 0, 1, 1), 480),
    ("voice-room", "voice-chat/voice-chat-03-voice-room", (0, 0, 1, 1), 480),
    ("voice-games", "voice-chat/voice-chat-05-games", (0, 0, 1, 1), 480),
    ("voice-friends", "voice-chat/voice-chat-06-friends", (0, 0, 1, 1), 480),
    ("voice-tictactoe", "voice-chat/voice-chat-04-game-tictactoe", (0, 0, 1, 1), 480),
    ("voice-leaderboard", "voice-chat/voice-chat-09-leaderboard", (0, 0, 1, 1), 480),
    ("anonka-settings", "anonka/anonka-03-settings", (0, 0, 1, 1), 360),
    ("anonka-bot", "anonka/anonka-04-bot-start", (0, 0, 1, 1), 360),
    ("checker-home", "checker/checker-01-miniapp-home", (0, 0, 1, 1), 360),
    ("checker-profile", "checker/checker-04-profile", (0, 0, 1, 1), 360),
    ("kachni-saved", "downloader/downloader-03-saved", (0, 0, 1, 1), 360),
    ("kachni-premium", "downloader/downloader-04-premium", (0, 0, 1, 1), 360),
    ("anonka-link", "anonka/anonka-01-link", (0, 0, 1, 1), 360),
    ("anonka-story", "anonka/anonka-02-story-card", (0, 0, 1, 1), 360),
    ("checker-clean", "checker/checker-02-report-clean-file", (0, 0, 1, 1), 360),
    ("checker-danger", "checker/checker-03-report-link", (0, 0, 1, 1), 360),
    ("kachni-home", "downloader/downloader-01-home", (0, 0, 1, 1), 360),
    ("kachni-player", "downloader/downloader-02-player", (0, 0, 1, 1), 360),
    ("evelone", "evelone/evelone-01-hero-desktop", (0, 0, 0.62, 0.62), 760),
    ("zvukpad", "zvukpad/zvukpad-06-editor-trim", (0, 0, 0.9, 0.9), 1100),
]


def prepare_fonts(font_dir):
    metrics = {}
    for name, file_name in [("sans", "Geist.ttf"), ("mono", "GeistMono.ttf")]:
        path = font_dir / file_name

        options = subset.Options()
        options.flavor = "woff2"
        options.layout_features = []
        options.name_IDs = []
        options.notdef_outline = True
        font = TTFont(path)
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=UNICODES)
        subsetter.subset(font)
        subset.save_font(font, SRC / f"{name}.woff2", options)

        metrics[name] = {}
        for weight in WEIGHTS:
            static = instancer.instantiateVariableFont(TTFont(path), {"wght": weight})
            cmap = static.getBestCmap()
            hmtx = static["hmtx"]
            scale = 1000 / static["head"].unitsPerEm
            metrics[name][str(weight)] = {
                chr(code): round(hmtx[cmap[code]][0] * scale) for code in UNICODES if code in cmap
            }
    (SRC / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, separators=(",", ":")))


def prepare_icons(icon_dir):
    icons = {}
    for path in sorted(icon_dir.glob("*.svg")):
        text = path.read_text()
        view_box = re.search(r'viewBox="([^"]+)"', text).group(1)
        paths = re.findall(r'<path[^>]* d="([^"]+)"', text)
        icons[path.stem] = {"viewBox": view_box, "d": " ".join(paths)}
    (SRC / "icons.json").write_text(json.dumps(icons, separators=(",", ":")))


def prepare_screens(screen_dir):
    out_dir = SRC / "img"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, source, box, width in SCREENS:
        for theme in ("light", "dark"):
            image = Image.open(screen_dir / f"{source}-{theme}.png").convert("RGB")
            left, top, right, bottom = box
            image = image.crop((
                round(left * image.width),
                round(top * image.height),
                round(right * image.width),
                round(bottom * image.height),
            ))
            height = round(image.height * width / image.width)
            image = image.resize((width, height), Image.LANCZOS)
            image.save(out_dir / f"{name}-{theme}.jpg", quality=84, optimize=True, progressive=True)


def catmull_rom(points):
    """Smooth a polyline into cubic Bezier segments through the same points."""
    if len(points) < 3:
        return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points)
    padded = [points[0]] + points + [points[-1]]
    parts = [f"M{points[0][0]:.1f} {points[0][1]:.1f}"]
    for index in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[index - 1], padded[index], padded[index + 1], padded[index + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        parts.append(f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    return "".join(parts)


def prepare_signature(font_path, word):
    """Single-stroke handwriting for the signature, as smoothed strokes in drawing order (y down)."""
    text = font_path.read_text()
    default_advance = float(re.search(r'<font [^>]*horiz-adv-x="([\d.]+)"', text).group(1))
    glyphs = {}
    for match in re.finditer(r"<glyph\b([^>]*?)/?>", text):
        attributes = match.group(1)
        char = re.search(r'unicode="([^"]*)"', attributes)
        if not char:
            continue
        path = re.search(r'\sd="([^"]*)"', attributes)
        advance = re.search(r'horiz-adv-x="([\d.]+)"', attributes)
        glyphs[char.group(1)] = (path.group(1) if path else "", float(advance.group(1)) if advance else default_advance)

    strokes = []
    cursor = 0.0
    for char in word:
        path, advance = glyphs[char]
        for subpath in re.split(r"(?=M)", path):
            numbers = [float(value) for value in re.findall(r"-?[\d.]+", subpath)]
            points = [(cursor + numbers[i], -numbers[i + 1]) for i in range(0, len(numbers) - 1, 2)]
            if len(points) < 2:
                continue
            length = sum(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 for (x1, y1), (x2, y2) in zip(points, points[1:]))
            strokes.append({"d": catmull_rom(points), "length": round(length, 1)})
        cursor += advance
    xs = [float(value) for stroke in strokes for value in re.findall(r"-?[\d.]+", stroke["d"])[0::2]]
    ys = [float(value) for stroke in strokes for value in re.findall(r"-?[\d.]+", stroke["d"])[1::2]]
    box = [min(xs), min(ys), max(xs), max(ys)]
    (SRC / "signature.json").write_text(json.dumps({"box": box, "strokes": strokes}, separators=(",", ":")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fonts", type=Path, required=True)
    parser.add_argument("--icons", type=Path, required=True)
    parser.add_argument("--screens", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True, help="EMSAllure.svg single-stroke font")
    args = parser.parse_args()

    SRC.mkdir(parents=True, exist_ok=True)
    prepare_fonts(args.fonts)
    prepare_icons(args.icons)
    prepare_screens(args.screens)
    prepare_signature(args.signature, "Denys")


if __name__ == "__main__":
    main()
