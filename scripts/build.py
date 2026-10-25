"""Render the profile cards (light and dark SVG) and README.md from profile.json.

Standard library only. Activity data comes from the GitHub GraphQL API when GITHUB_TOKEN
is set, otherwise from the cached assets/src/activity.json.

    python scripts/build.py
"""

import base64
import datetime as dt
import json
import math
import os
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "src"
OUT = ROOT / "assets"

PROFILE = json.loads((ROOT / "profile.json").read_text())
METRICS = json.loads((SRC / "metrics.json").read_text())
ICONS = json.loads((SRC / "icons.json").read_text())
SIGNATURE = json.loads((SRC / "signature.json").read_text())
FONTS = {name: base64.b64encode((SRC / f"{name}.woff2").read_bytes()).decode() for name in ("sans", "mono")}

WIDTH = 840
PAIR_WIDTH = 412
RADIUS = 28
EASE = "cubic-bezier(.2,.7,.2,1)"
SPRING = "cubic-bezier(.34,1.56,.64,1)"

THEMES = {
    "light": {
        "card": "#f5f5f7",
        "tile": "#ffffff",
        "text": "#1d1d1f",
        "muted": "#6e6e73",
        "faint": "#86868b",
        "line": "#d2d2d7",
        "accent": "#0071e3",
        "accentText": "#ffffff",
        "green": "#28a745",
        "amber": "#c77700",
        "bezel": "#1d1d1f",
        "bezelEdge": "#1d1d1f",
        "heat": ["#e3e3e8", "#b5d3f5", "#7ab2ee", "#3a8de6", "#0071e3"],
        "shadow": 0.16,
        "glow": 0.17,
    },
    "dark": {
        "card": "#1c1c1e",
        "tile": "#2c2c2e",
        "text": "#f5f5f7",
        "muted": "#a1a1a6",
        "faint": "#8d8d93",
        "line": "#3a3a3c",
        "accent": "#2997ff",
        "accentText": "#ffffff",
        "green": "#30d158",
        "amber": "#ffb340",
        "bezel": "#000000",
        "bezelEdge": "#48484a",
        "heat": ["#2c2c2e", "#103a66", "#185a9e", "#1f7ad6", "#2997ff"],
        "shadow": 0.45,
        "glow": 0.16,
    },
}


# Text measurement and layout

def text_width(text, size, weight=400, family="sans", tracking=0.0):
    table = METRICS[family][str(weight)]
    units = sum(table.get(char, 600) for char in text)
    return units * size / 1000 + tracking * size * len(text)


def wrap(text, size, max_width, weight=400, family="sans"):
    lines = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and text_width(candidate, size, weight, family) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def text(x, y, content, size, fill, weight=400, family="sans", tracking=0.0, anchor="start", extra=""):
    family_class = ' class="m"' if family == "mono" else ""
    letter_spacing = f' letter-spacing="{tracking}em"' if tracking else ""
    text_anchor = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{fill}"'
        f"{family_class}{letter_spacing}{text_anchor}{extra}>{escape(content)}</text>"
    )


def paragraph(x, y, content, size, max_width, line_height, fill, weight=400):
    lines = wrap(content, size, max_width, weight)
    parts = [text(x, y + index * line_height, line, size, fill, weight) for index, line in enumerate(lines)]
    return "".join(parts), y + (len(lines) - 1) * line_height


def eyebrow(x, y, content, fill):
    return text(x, y, content.upper(), 12, fill, 500, "mono", 0.08)


# Drawing primitives

def icon(name, x, y, size, fill):
    data = ICONS[name]
    return (
        f'<svg x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" viewBox="{data["viewBox"]}">'
        f'<path d="{data["d"]}" fill="{fill}"/></svg>'
    )


def linkedin_icon(x, y, size, fill, background):
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" rx="{size * 0.22:.1f}" fill="{fill}"/>'
        + text(x + size * 0.5, y + size * 0.76, "in", size * 0.7, background, 700, anchor="middle", tracking=-0.02)
    )


def any_icon(name, x, y, size, fill, background):
    if name == "linkedin":
        return linkedin_icon(x, y, size, fill, background)
    return icon(name, x, y, size, fill)


def image_data(name, theme):
    data = base64.b64encode((SRC / "img" / f"{name}-{theme}.jpg").read_bytes()).decode()
    return f"data:image/jpeg;base64,{data}"


def image_ratio(name):
    # JPEG size from the SOF marker, so build.py needs no imaging library
    raw = (SRC / "img" / f"{name}-light.jpg").read_bytes()
    index = 2
    while index < len(raw):
        marker = raw[index + 1]
        length = int.from_bytes(raw[index + 2:index + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2):
            height = int.from_bytes(raw[index + 5:index + 7], "big")
            width = int.from_bytes(raw[index + 7:index + 9], "big")
            return height / width
        index += 2 + length
    raise ValueError(f"no frame header in {name}")


def rise(content, delay, distance=""):
    variant = f" r{distance}" if distance else ""
    return f'<g class="r{variant}" style="animation-delay:{delay:.2f}s">{content}</g>'


def spring(content, delay):
    return f'<g class="s" style="animation-delay:{delay:.2f}s">{content}</g>'


def odometer(x, y, value, size, fill, delay, clip_id, weight=700, tracking=-0.04):
    """Digits roll up into place like a mechanical counter. Without animation the final value shows."""
    line = size * 1.2
    parts = [f'<clipPath id="{clip_id}"><rect x="{x - 4:.1f}" y="{y - size:.1f}" width="{text_width(value, size, weight, tracking=tracking) + 12:.1f}" height="{size * 1.25:.1f}"/></clipPath>']
    parts.append(f'<g clip-path="url(#{clip_id})">')
    cursor = x
    for index, char in enumerate(value):
        width = text_width(char, size, weight, tracking=tracking)
        if char.isdigit():
            target = 10 + int(char)
            column = "".join(text(cursor, y + row * line, str(row % 10), size, fill, weight, tracking=tracking) for row in range(target + 1))
            parts.append(
                f'<g class="odo" transform="translate(0 {-target * line:.1f})" style="animation-delay:{delay + index * 0.12:.2f}s">{column}</g>'
            )
        else:
            parts.append(text(cursor, y, char, size, fill, weight, tracking=tracking))
        cursor += width
    parts.append("</g>")
    return "".join(parts)


def phone(x, y, width, screens, theme, palette, clip_id, card_height, phase=0.0, period=9.0):
    """A phone that runs past the bottom edge of the card. Extra screens fade in on a loop, like the app in use."""
    if isinstance(screens, str):
        screens = [screens]
    bezel = 6
    inner = width - bezel * 2
    radius = 30
    images = []
    for index, screen in enumerate(screens):
        screen_height = inner * image_ratio(screen)
        if y + bezel + screen_height < card_height:
            raise ValueError(f"{screen}: screenshot ends {card_height - y - bezel - screen_height:.0f}px above the card edge")
        cycle = ""
        if index:
            start = phase + (index - 1) * period
            cycle = f' class="cyc" opacity="0" style="animation:cycle {period * (len(screens) - 1):.1f}s ease-in-out {start:.2f}s infinite"'
        images.append(
            f'<image{cycle} href="{image_data(screen, theme)}" x="{x + bezel:.1f}" y="{y + bezel:.1f}" width="{inner:.1f}" '
            f'height="{screen_height:.1f}" preserveAspectRatio="xMidYMin slice"/>'
        )
    height = card_height - y + 60
    return (
        f'<clipPath id="{clip_id}"><rect x="{x + bezel:.1f}" y="{y + bezel:.1f}" width="{inner:.1f}" '
        f'height="{height:.1f}" rx="{radius - bezel}"/></clipPath>'
        f'<g filter="url(#shadow)"><rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" rx="{radius}" '
        f'fill="{palette["bezel"]}" stroke="{palette["bezelEdge"]}" stroke-width="1"/></g>'
        f'<g clip-path="url(#{clip_id})"><rect x="{x + bezel:.1f}" y="{y + bezel:.1f}" width="{inner:.1f}" height="{height:.1f}" fill="{palette["card"]}"/>'
        + "".join(images)
        + "</g>"
    )


def floating(content, delay):
    return f'<g class="float" style="animation-delay:{delay:.2f}s">{content}</g>'


def arrow_badge(x, y, palette):
    return (
        f'<circle cx="{x}" cy="{y}" r="17" fill="{palette["tile"]}"/>'
        + icon("ms-north_east", x - 9, y - 9, 18, palette["text"])
    )


def document(width, height, body, theme, title, extra_css="", card=True, gutter=0, offset=0):
    palette = THEMES[theme]
    background = (
        f'<rect width="{width}" height="{height}" rx="{RADIUS}" fill="{palette["card"]}"/>' if card else ""
    )
    clip_open = f'<g clip-path="url(#card)">' if card else "<g>"
    css = (
        'text{font-family:S,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-kerning:none;white-space:pre}'
        '.m{font-family:M,ui-monospace,SFMono-Regular,monospace}'
        f".r{{animation:rise 1s {EASE} both}}"
        f".r2{{animation-name:rise2;animation-duration:1.2s}}"
        f".p{{animation:pop .9s {EASE} both;transform-box:fill-box;transform-origin:center}}"
        f".s{{animation:spring .8s {SPRING} both;transform-box:fill-box;transform-origin:center}}"
        ".float{animation:float 5s ease-in-out infinite alternate}"
        ".ping{transform-box:fill-box;transform-origin:center;animation:ping 2s ease-out infinite}"
        f".odo{{animation:roll 1.8s cubic-bezier(.16,1,.3,1) both}}"
        "@keyframes rise{from{opacity:0;transform:translateY(14px)}}"
        "@keyframes rise2{from{opacity:0;transform:translateY(48px)}}"
        "@keyframes pop{from{opacity:0;transform:scale(.86)}}"
        "@keyframes spring{from{opacity:0;transform:scale(.6)}}"
        "@keyframes float{to{transform:translateY(-9px)}}"
        "@keyframes ping{from{opacity:.6;transform:scale(1)}to{opacity:0;transform:scale(2.8)}}"
        "@keyframes roll{from{transform:translateY(0)}}"
        "@keyframes cycle{0%,44%{opacity:0;transform:translateY(14px)}52%,94%{opacity:1;transform:none}100%{opacity:0;transform:none}}"
        + extra_css
        + "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
    )
    fonts = "".join(
        f'@font-face{{font-family:{family};src:url(data:font/woff2;base64,{FONTS[name]}) format("woff2");font-weight:100 900}}'
        for name, family in (("sans", "S"), ("mono", "M"))
        if (name == "sans" and "<text" in body) or 'class="m"' in body
    )
    css = fonts + css
    outer = width + gutter
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{outer}" height="{height}" viewBox="0 0 {outer} {height}" '
        f'role="img" aria-label="{escape(title)}" fill="none">'
        f"<title>{escape(title)}</title><style>{css}</style>"
        f'<defs><clipPath id="card"><rect width="{width}" height="{height}" rx="{RADIUS}"/></clipPath>'
        f'<filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feDropShadow dx="0" dy="14" stdDeviation="16" flood-color="#000" flood-opacity="{palette["shadow"]}"/></filter></defs>'
        f'<g transform="translate({offset} 0)">{background}{clip_open}{body}</g></g></svg>'
    )


# Cards

def render_hero(theme):
    palette = THEMES[theme]
    hero = PROFILE["hero"]
    text_x = 268
    text_width_max = WIDTH - text_x - 44

    monogram_x = 136 - text_width("DZ", 88, 800, tracking=-0.04) / 2
    avatar = (
        '<linearGradient id="avatar" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#1f5fd6"/><stop offset=".5" stop-color="#2f7cf0"/>'
        '<stop offset="1" stop-color="#5aa6ff"/></linearGradient>'
        '<radialGradient id="avatarLight" cx=".72" cy=".3" r=".6">'
        '<stop offset="0" stop-color="#fff" stop-opacity=".28"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        '<g class="p" style="animation-delay:.05s">'
        '<rect x="44" y="52" width="184" height="184" rx="52" fill="url(#avatar)"/>'
        '<rect x="44" y="52" width="184" height="184" rx="52" fill="url(#avatarLight)"/>'
        f'{text(monogram_x, 175, "D", 88, "#ffffff", 800, tracking=-0.04)}'
        f'{text(monogram_x + text_width("D", 88, 800, tracking=-0.04), 175, "Z", 88, "#c9e4ff", 800, tracking=-0.04)}'
        # A glass highlight sweeps across the tile every few seconds
        '<clipPath id="tile"><rect x="44" y="52" width="184" height="184" rx="52"/></clipPath>'
        '<linearGradient id="sheenFill" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".42"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        '<g clip-path="url(#tile)"><path class="sheen" d="M-40 20 L20 20 L-60 280 L-120 280 Z" fill="url(#sheenFill)"/></g>'
        "</g>"
    )

    # Three soft light pools drift on different periods, so the motion never repeats exactly
    pools = [
        (palette["accent"], 720, 30, 250, "a1", 1.0),
        ("#5ac8fa", 560, 300, 210, "a2", 0.8),
        ("#9ec9ff", 840, 260, 190, "a3", 0.7),
    ]
    glow = ""
    for color, cx, cy, radius, name, strength in pools:
        glow += (
            f'<radialGradient id="{name}g" cx=".5" cy=".5" r=".5">'
            f'<stop offset="0" stop-color="{color}" stop-opacity="{palette["glow"] * strength:.3f}"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>'
            f'<g class="{name}"><circle cx="{cx}" cy="{cy}" r="{radius}" fill="url(#{name}g)"/></g>'
        )

    rings = "".join(
        f'<rect class="speak" style="animation-delay:{1.2 + index * 1.4:.1f}s" x="44" y="52" width="184" height="184" rx="52" '
        f'stroke="{palette["accent"]}" stroke-width="2"/>'
        for index in range(2)
    )
    parts = [glow, rings, avatar]
    parts.append(rise(eyebrow(text_x, 84, hero["eyebrow"], palette["muted"]), 0.12))
    # The name comes in letter by letter while the weight grows from light to bold
    letter_x = text_x
    for index, char in enumerate(hero["name"]):
        if char != " ":
            parts.append(
                f'<g class="ltr" style="animation-delay:{0.18 + index * 0.045:.3f}s">'
                + text(letter_x, 140, char, 54, palette["text"], 700, tracking=-0.035)
                + "</g>"
            )
        letter_x += text_width(char, 54, 700, tracking=-0.035)
    subtitle, last_y = paragraph(text_x, 178, hero["subtitle"], 18, text_width_max, 26, palette["muted"])
    parts.append(rise(subtitle, 0.28))

    chip_x = text_x
    chip_y = last_y + 26
    chips = []
    for index, chip in enumerate(hero["chips"]):
        label_width = text_width(chip["label"], 14, 500)
        width = 14 + 16 + 8 + label_width + 16
        if chip_x + width > WIDTH - 40:
            chip_x = text_x
            chip_y += 42
        if chip["icon"] == "status":
            mark = (
                f'<circle cx="{chip_x + 22}" cy="{chip_y + 17}" r="4.5" fill="{palette["green"]}"/>'
                f'<circle class="ping" cx="{chip_x + 22}" cy="{chip_y + 17}" r="4.5" fill="{palette["green"]}"/>'
            )
        else:
            mark = icon(chip["icon"], chip_x + 14, chip_y + 9, 16, palette["muted"])
        chip_svg = (
            f'<rect x="{chip_x:.1f}" y="{chip_y:.1f}" width="{width:.1f}" height="34" rx="17" fill="{palette["tile"]}"/>'
            + mark
            + text(chip_x + 38, chip_y + 22, chip["label"], 14, palette["text"], 500)
        )
        chips.append(spring(chip_svg, 0.75 + index * 0.1))
        chip_x += width + 8
    parts.extend(chips)

    height = round(max(chip_y + 34 + 44, 288))
    extra_css = (
        f".ltr{{animation:rise 1s {EASE} both}}"
        f".ltr text{{font-weight:700;animation:wght 1.8s {EASE} both;animation-delay:inherit}}"
        "@keyframes wght{from{font-weight:200}}"
        ".sheen{animation:sheen 6s cubic-bezier(.4,0,.2,1) 1.4s infinite}"
        ".speak{opacity:0;transform-box:fill-box;transform-origin:center;animation:speak 2.8s cubic-bezier(.2,.7,.2,1) infinite}"
        "@keyframes speak{0%{opacity:.55;transform:scale(1)}100%{opacity:0;transform:scale(1.22)}}"
        "@keyframes sheen{0%{transform:translateX(0)}28%,100%{transform:translateX(380px)}}"
        ".a1{animation:a1 17s ease-in-out infinite}.a2{animation:a2 23s ease-in-out infinite}.a3{animation:a3 29s ease-in-out infinite}"
        "@keyframes a1{33%{transform:translate(-140px,70px)}66%{transform:translate(-40px,120px)}}"
        "@keyframes a2{50%{transform:translate(180px,-120px)}}"
        "@keyframes a3{40%{transform:translate(-220px,-60px)}80%{transform:translate(-90px,-150px)}}"
    )
    title = f'{hero["name"]}. {hero["subtitle"]}'
    return document(WIDTH, height, "".join(parts), theme, title, extra_css)


def link_width(link):
    return 16 + 18 + 9 + text_width(link["label"], 15, 500) + 8 + 14 + 16 + 8


def render_link(link, index, theme):
    palette = THEMES[theme]
    width = link_width(link)
    pill_width = width - 8
    label_x = 4 + 16 + 18 + 9
    arrow_x = 4 + pill_width - 16 - 14
    body = (
        f'<rect x="4" y="2" width="{pill_width:.1f}" height="44" rx="22" fill="{palette["card"]}"/>'
        + any_icon(link["icon"], 20, 15, 18, palette["text"], palette["card"])
        + text(label_x, 29.5, link["label"], 15, palette["text"], 500)
        + icon("ms-north_east", arrow_x, 17, 14, palette["faint"])
    )
    return document(round(width), 48, spring(body, 0.5 + index * 0.08), theme, link["label"], card=False)


def render_now(theme):
    palette = THEMES[theme]
    now = PROFILE["now"]
    parts = [rise(text(40, 60, now["title"], 26, palette["text"], 700, tracking=-0.02), 0.05)]
    y = 88
    for index, item in enumerate(now["items"]):
        row = (
            f'<rect x="24" y="{y}" width="{WIDTH - 48}" height="48" rx="16" fill="{palette["tile"]}"/>'
            f'<circle cx="52" cy="{y + 24}" r="14" fill="{palette["card"]}"/>'
            + icon(item["icon"], 43, y + 15, 18, palette["text"])
            + text(80, y + 29.5, item["label"], 15.5, palette["text"], 500)
        )
        if item.get("live"):
            label_width = text_width(item["live"], 12, 600, "mono", 0.06)
            row += (
                f'<circle cx="{WIDTH - 52 - label_width - 14}" cy="{y + 24}" r="4" fill="{palette["green"]}"/>'
                f'<circle class="ping" cx="{WIDTH - 52 - label_width - 14}" cy="{y + 24}" r="4" fill="{palette["green"]}"/>'
                + text(WIDTH - 52, y + 28.5, item["live"], 12, palette["green"], 600, "mono", 0.06, anchor="end")
            )
        parts.append(rise(row, 0.12 + index * 0.07))
        y += 56
    return document(WIDTH, y + 18, "".join(parts), theme, now["title"])


def render_voice(theme):
    """A live voice level across the page: the products are about voice, so this is the divider."""
    palette = THEMES[theme]
    height = 72
    bars = 88
    pitch = WIDTH / bars
    parts = [
        f'<linearGradient id="fade" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{WIDTH}" y2="0">'
        f'<stop offset="0" stop-color="{palette["accent"]}" stop-opacity="0"/>'
        f'<stop offset=".18" stop-color="{palette["accent"]}" stop-opacity=".9"/>'
        f'<stop offset=".5" stop-color="#5ac8fa"/>'
        f'<stop offset=".82" stop-color="{palette["accent"]}" stop-opacity=".9"/>'
        f'<stop offset="1" stop-color="{palette["accent"]}" stop-opacity="0"/></linearGradient>'
    ]
    for index in range(bars):
        position = index / (bars - 1)
        envelope = math.sin(math.pi * position) ** 0.7
        texture = 0.55 + 0.45 * math.sin(index * 0.9) * math.cos(index * 0.37)
        bar_height = max(4, 6 + 52 * envelope * abs(texture))
        x = index * pitch + (pitch - 3) / 2
        delay = -((index * 0.137 + math.sin(index) * 0.4) % 1.6)
        duration = 1.1 + (index % 5) * 0.12
        parts.append(
            f'<rect class="eq" style="animation-duration:{duration:.2f}s;animation-delay:{delay:.2f}s" x="{x:.1f}" '
            f'y="{(height - bar_height) / 2:.1f}" width="3" height="{bar_height:.1f}" rx="1.5" fill="url(#fade)"/>'
        )
    extra_css = (
        ".eq{transform-box:fill-box;transform-origin:center;animation:eq 1.4s ease-in-out infinite alternate}"
        "@keyframes eq{from{transform:scaleY(.18)}to{transform:scaleY(1)}}"
    )
    return document(WIDTH, height, "".join(parts), theme, "", extra_css, card=False)


def render_section(section, theme):
    palette = THEMES[theme]
    parts = [
        rise(text(4, 20, section["index"], 13, palette["accent"], 600, "mono", 0.06), 0.0),
        rise(text(2, 66, section["title"], 40, palette["text"], 700, tracking=-0.035), 0.06),
    ]
    note, last_y = paragraph(4, 98, section["note"], 16, WIDTH - 8, 24, palette["muted"])
    parts.append(rise(note, 0.12))
    return document(WIDTH, round(last_y + 14), "".join(parts), theme, f'{section["title"]}. {section["note"]}', card=False)


def project_text(project, x, y, max_width, title_size, palette):
    parts = [rise(eyebrow(x, y, project["eyebrow"], palette["accent"]), 0.05)]
    title_lines = wrap(project["title"], title_size, max_width, 700)
    title_y = y + title_size + 10
    for index, line in enumerate(title_lines):
        parts.append(rise(text(x, title_y + index * title_size * 1.1, line, title_size, palette["text"], 700, tracking=-0.03), 0.1))
    title_bottom = title_y + (len(title_lines) - 1) * title_size * 1.1
    body_size = 16 if title_size > 28 else 15
    body, last_y = paragraph(x, title_bottom + 32, project["text"], body_size, max_width, body_size * 1.5, palette["muted"])
    parts.append(rise(body, 0.16))
    stack_lines = wrap(project["stack"], 11.5, max_width, 500, "mono")
    stack_y = last_y + 30
    for index, line in enumerate(stack_lines):
        parts.append(rise(text(x, stack_y + index * 18, line, 11.5, palette["faint"], 500, "mono"), 0.22))
    return "".join(parts), stack_y + (len(stack_lines) - 1) * 18


def render_featured(theme):
    palette = THEMES[theme]
    project = PROFILE["featured"]
    parts = []
    block, bottom = project_text(project, 40, 58, 420, 34, palette)
    parts.append(block)

    fact_x = 540
    for index, fact in enumerate(project["facts"]):
        x = fact_x + index * 136
        fact_svg = odometer(x, 112, fact["value"], 56, palette["text"], 0.5 + index * 0.15, f"fact{index}")
        label, _ = paragraph(x, 140, fact["label"], 14, 116, 19, palette["muted"])
        parts.append(rise(fact_svg + label, 0.2 + index * 0.06))
    cta_y = 212
    cta = (
        text(fact_x, cta_y, project["cta"], 15, palette["accent"], 600)
        + icon("ms-north_east", fact_x + text_width(project["cta"], 15, 600) + 4, cta_y - 13, 15, palette["accent"])
    )
    parts.append(rise(cta, 0.3))
    parts.append(arrow_badge(WIDTH - 44, 44, palette))

    phone_width = 212
    gap = 26
    start_x = (WIDTH - (phone_width * 3 + gap * 2)) / 2
    top = max(bottom, cta_y) + 44
    offsets = [40, 0, 40]
    height = round(top + 320)
    for index, screens in enumerate(project["screens"]):
        x = start_x + index * (phone_width + gap)
        device = phone(x, top + offsets[index], phone_width, screens, theme, palette, f"screen{index}", height, phase=2.2 + index * 1.4)
        parts.append(rise(floating(device, -index * 1.7), 0.3 + index * 0.1, "2"))
    title = f'{project["title"]}. {project["text"]}'
    return document(WIDTH, height, "".join(parts), theme, title)


def browser(x, y, width, screen, theme, palette):
    bar = 30
    image_height = width * image_ratio(screen)
    dots = "".join(
        f'<circle cx="{x + 18 + index * 16}" cy="{y + bar / 2}" r="5" fill="{palette["line"]}"/>' for index in range(3)
    )
    return (
        f'<clipPath id="window"><rect x="{x}" y="{y}" width="{width}" height="{bar + image_height:.1f}" rx="14"/></clipPath>'
        f'<g filter="url(#shadow)"><rect x="{x}" y="{y}" width="{width}" height="{bar + image_height:.1f}" rx="14" fill="{palette["tile"]}"/></g>'
        f'<g clip-path="url(#window)">{dots}'
        f'<image href="{image_data(screen, theme)}" x="{x}" y="{y + bar}" width="{width}" height="{image_height:.1f}"/></g>'
    )


def render_pair_card(project, theme, height, side):
    palette = THEMES[theme]
    parts = []
    block, bottom = project_text(project, 28, 50, PAIR_WIDTH - 56 - 30, 26, palette)
    parts.append(block)
    parts.append(arrow_badge(PAIR_WIDTH - 40, 40, palette))
    top = bottom + 34
    if "screens" in project:
        phone_width = 170
        gap = 16
        start_x = (PAIR_WIDTH - (phone_width * 2 + gap)) / 2
        for index, screens in enumerate(project["screens"]):
            x = start_x + index * (phone_width + gap)
            device = phone(x, top + index * 28, phone_width, screens, theme, palette, f"screen{index}", height, phase=3.0 + side * 2.1 + index * 1.3)
            parts.append(rise(floating(device, -index * 1.9 - side), 0.28 + index * 0.1, "2"))
    else:
        window_width = 560
        if top + 6 + 30 + window_width * image_ratio(project["browser"]) < height + 20:
            raise ValueError(f'{project["id"]}: browser window does not reach the card edge')
        parts.append(rise(floating(browser(28, top + 6, window_width, project["browser"], theme, palette), -2.4), 0.28, "2"))
    if height - top < 200:
        raise ValueError(f'{project["id"]}: only {height - top:.0f}px left for screenshots')
    title = f'{project["title"]}. {project["text"]}'
    return document(PAIR_WIDTH, height, "".join(parts), theme, title, gutter=8, offset=8 if side else 0)


def render_zvukpad(theme):
    palette = THEMES[theme]
    project = PROFILE["zvukpad"]
    parts = []
    block, bottom = project_text(project, 40, 58, 290, 34, palette)
    parts.append(block)
    status_y = bottom + 26
    status_width = 14 + 8 + 8 + text_width(project["status"], 13, 600) + 14
    status = (
        f'<rect x="40" y="{status_y:.1f}" width="{status_width:.1f}" height="30" rx="15" fill="{palette["tile"]}"/>'
        f'<circle cx="58" cy="{status_y + 15:.1f}" r="4" fill="{palette["amber"]}"/>'
        f'<circle class="ping" cx="58" cy="{status_y + 15:.1f}" r="4" fill="{palette["amber"]}"/>'
        + text(70, status_y + 20, project["status"], 13, palette["text"], 600)
    )
    parts.append(rise(status, 0.26))

    window_x = 360
    window_y = 64
    window_width = 600
    window_height = window_width * image_ratio(project["screen"])
    window = (
        f'<clipPath id="window"><rect x="{window_x}" y="{window_y}" width="{window_width}" height="{window_height:.1f}" rx="14"/></clipPath>'
        f'<g filter="url(#shadow)"><rect x="{window_x}" y="{window_y}" width="{window_width}" height="{window_height:.1f}" rx="14" '
        f'fill="{palette["tile"]}" stroke="{palette["line"]}"/></g>'
        f'<image href="{image_data(project["screen"], theme)}" x="{window_x}" y="{window_y}" width="{window_width}" '
        f'height="{window_height:.1f}" clip-path="url(#window)"/>'
    )
    parts.append(rise(floating(window, -1.2), 0.3, "2"))
    height = max(round(status_y + 30 + 44), 400)
    extra_css = (
        "@keyframes ping{from{opacity:.6;transform:scale(1)}to{opacity:0;transform:scale(2.8)}}"
        ".ping{transform-box:fill-box;transform-origin:center;animation:ping 2s ease-out infinite}"
    )
    title = f'{project["title"]}, {project["status"].lower()}. {project["text"]}'
    return document(WIDTH, height, "".join(parts), theme, title, extra_css)


def demo_frames(demo):
    """Field states for the inkey demo: (typed so far, fixed words, flash index)."""
    frames = []
    fixed = []
    for word in demo:
        for count in range(1, len(word["typed"]) + 1):
            frames.append((" ".join(fixed), word["typed"][:count], False))
        fixed.append(word["fixed"])
        frames.append((" ".join(fixed), "", True))
    return frames


def render_inkey(theme):
    palette = THEMES[theme]
    project = PROFILE["inkey"]
    parts = []
    block, bottom = project_text(project, 40, 58, 360, 34, palette)
    parts.append(block)
    cta_y = bottom + 34
    cta = (
        text(40, cta_y, project["cta"], 15, palette["accent"], 600)
        + icon("ms-north_east", 40 + text_width(project["cta"], 15, 600) + 4, cta_y - 13, 15, palette["accent"])
    )
    parts.append(rise(cta, 0.3))

    panel_x = 448
    panel_y = 40
    panel_width = WIDTH - panel_x - 40
    height = max(round(cta_y + 46), 300)
    panel_height = height - panel_y * 2
    field_y = panel_y + 66
    field_x = panel_x + 24
    field_width = panel_width - 48

    frames = demo_frames(project["demo"])
    step = 0.16
    hold_fixed = 0.9
    durations = [hold_fixed if flash else step for _, _, flash in frames]
    durations[-1] = 2.6
    lead = 0.6
    total = lead + sum(durations) + 0.4

    css = []
    frame_svgs = []
    start = lead
    space_times = []
    for index, (fixed, typed, flash) in enumerate(frames):
        end = start + durations[index]
        content_x = field_x + 18
        spans = []
        if fixed:
            spans.append(f'<tspan fill="{palette["text"]}">{escape(fixed)}</tspan>')
        if typed:
            prefix = " " if fixed else ""
            spans.append(f'<tspan fill="{palette["amber"]}">{escape(prefix + typed)}</tspan>')
        visible = (fixed + (" " if fixed and typed else "") + typed)
        caret_x = content_x + text_width(visible, 20, 500, "mono") + 2
        caret = f'<rect class="caret" x="{caret_x:.1f}" y="{field_y + 15}" width="2" height="24" rx="1" fill="{palette["accent"]}"/>'
        last = index == len(frames) - 1
        frame_svgs.append(
            f'<g class="f{index}" opacity="{1 if last else 0}">'
            f'<text x="{content_x}" y="{field_y + 34}" font-size="20" font-weight="500" class="m">{"".join(spans)}</text>{caret}</g>'
        )
        on = start / total * 100
        off = end / total * 100
        if last:
            css.append(f"@keyframes f{index}{{0%{{opacity:0}}{on:.2f}%{{opacity:1}}{(total - 0.3) / total * 100:.2f}%{{opacity:0}}}}")
        else:
            css.append(f"@keyframes f{index}{{0%{{opacity:0}}{on:.2f}%{{opacity:1}}{off:.2f}%{{opacity:0}}}}")
        css.append(f".f{index}{{animation:f{index} {total:.2f}s step-end infinite}}")
        if flash:
            space_times.append(start)
        start = end

    key_frames = ["0%{transform:none}"]
    fill_frames = ["0%{fill:var(--k)}"]
    for moment in space_times:
        on = moment / total * 100
        key_frames.append(f"{on - 0.4:.2f}%{{transform:none}}{on:.2f}%{{transform:translateY(3px)}}{on + 4:.2f}%{{transform:none}}")
        fill_frames.append(f"{on - 0.4:.2f}%{{fill:var(--k)}}{on:.2f}%{{fill:{palette['accent']}}}{on + 4:.2f}%{{fill:var(--k)}}")
    css.append(f"@keyframes key{{{''.join(key_frames)}}}")
    css.append(f".key{{--k:{palette['card']};animation:key {total:.2f}s linear infinite}}.key rect{{fill:var(--k);animation:inherit;animation-name:keyfill}}")
    css.append(f"@keyframes keyfill{{{''.join(fill_frames)}}}")
    css.append("@keyframes blink{50%{opacity:0}}.caret{animation:blink 1s step-end infinite}")
    css.append(f"@media (prefers-reduced-motion:reduce){{[class^=f]{{opacity:0}}.f{len(frames) - 1}{{opacity:1}}}}")

    key_width = 150
    key_x = panel_x + (panel_width - key_width) / 2
    key_y = field_y + 54 + 36
    panel = (
        f'<rect x="{panel_x}" y="{panel_y}" width="{panel_width}" height="{panel_height}" rx="22" fill="{palette["tile"]}"/>'
        + text(panel_x + 24, panel_y + 36, "DEMO", 11, palette["faint"], 500, "mono", 0.1)
        + text(panel_x + panel_width - 24, panel_y + 36, "EN layout → RU word", 11, palette["faint"], 500, "mono", 0.02, anchor="end")
        + f'<rect x="{field_x}" y="{field_y}" width="{field_width}" height="54" rx="14" fill="{palette["card"]}" stroke="{palette["line"]}"/>'
        + "".join(frame_svgs)
        + f'<g class="key"><rect x="{key_x:.1f}" y="{key_y}" width="{key_width}" height="40" rx="10" stroke="{palette["line"]}"/>'
        + text(key_x + key_width / 2, key_y + 25, "space", 13, palette["muted"], 500, "mono", anchor="middle")
        + "</g>"
        + text(panel_x + panel_width / 2, key_y + 68, "The word is checked when you press space", 13, palette["faint"], 400, anchor="middle")
    )
    parts.append(rise(panel, 0.2))
    title = f'{project["title"]}. {project["text"]} Demo: typing ghbdtn gives привет.'
    return document(WIDTH, height, "".join(parts), theme, title, "".join(css))


def render_stack(theme):
    palette = THEMES[theme]
    stack = PROFILE["stack"]
    parts = [rise(text(40, 60, stack["title"], 26, palette["text"], 700, tracking=-0.02), 0.05)]
    y = 92
    chip_start = 176
    delay = 0.1
    for group in stack["groups"]:
        parts.append(rise(text(40, y + 22, group["title"].upper(), 11.5, palette["faint"], 500, "mono", 0.08), delay))
        x = chip_start
        for icon_name, label in group["items"]:
            width = 12 + 16 + 8 + text_width(label, 14, 500) + 14
            if x + width > WIDTH - 40:
                x = chip_start
                y += 44
            chip = (
                f'<rect x="{x:.1f}" y="{y}" width="{width:.1f}" height="34" rx="10" fill="{palette["tile"]}"/>'
                + icon(icon_name, x + 12, y + 9, 16, palette["text"])
                + text(x + 36, y + 22, label, 14, palette["text"], 500)
            )
            parts.append(spring(chip, delay))
            delay += 0.03
            x += width + 8
        y += 46
    return document(WIDTH, y + 22, "".join(parts), theme, "Stack: " + ", ".join(
        label for group in stack["groups"] for _, label in group["items"]
    ))


# Activity

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}
"""

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def fetch_activity():
    cache = SRC / "activity.json"
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return json.loads(cache.read_text())
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": PROFILE["login"]}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-build"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    calendar = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [
        {"date": day["date"], "count": day["contributionCount"], "level": LEVELS[day["contributionLevel"]]}
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    ]
    activity = {"total": calendar["totalContributions"], "days": days}
    cache.write_text(json.dumps(activity, separators=(",", ":")) + "\n")
    return activity


def streaks(days, today):
    """Current streak counts back from today, or from yesterday if today has no contributions yet."""
    counts = {dt.date.fromisoformat(day["date"]): day["count"] for day in days}
    longest = 0
    run = 0
    for date in sorted(counts):
        run = run + 1 if counts[date] > 0 else 0
        longest = max(longest, run)
    cursor = today if counts.get(today, 0) > 0 else today - dt.timedelta(days=1)
    current = 0
    while counts.get(cursor, 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)
    return current, longest


def render_activity(theme, activity):
    palette = THEMES[theme]
    copy = PROFILE["activity"]
    days = activity["days"]
    today = dt.date.fromisoformat(days[-1]["date"])
    current, longest = streaks(days, today)

    parts = [
        rise(text(40, 60, copy["title"], 26, palette["text"], 700, tracking=-0.02), 0.05),
    ]
    parts.append(odometer(40, 138, f'{activity["total"]:,}', 60, palette["text"], 0.3, "total"))
    parts.append(rise(text(40, 166, copy["contributions"], 15, palette["muted"]), 0.14))

    active_days = sum(1 for day in days if day["count"] > 0)
    # A streak of 0 or 1 says nothing, show how many days had contributions instead
    first_tile = (copy["current"], current) if current >= 2 else (copy["active"], active_days)
    for index, (label, value) in enumerate([first_tile, (copy["longest"], longest)]):
        x = 40 + index * 172
        unit = copy["days"] if value != 1 else copy["days"].rstrip("s")
        number_width = text_width(str(value), 30, 700, tracking=-0.03)
        tile = (
            f'<rect x="{x}" y="196" width="160" height="84" rx="18" fill="{palette["tile"]}"/>'
            + odometer(x + 18, 236, str(value), 30, palette["text"], 0.6 + index * 0.2, f"tile{index}", tracking=-0.03)
            + text(x + 18 + number_width + 6, 236, unit, 14, palette["muted"], 500)
            + text(x + 18, 262, label, 13, palette["muted"])
        )
        parts.append(rise(tile, 0.2 + index * 0.06))

    weeks = copy["weeks"]
    cell = 14
    gap = 4
    grid_width = weeks * (cell + gap) - gap
    grid_x = WIDTH - 40 - grid_width
    grid_y = 112
    # Align to whole weeks ending on the last day, Sunday first like GitHub
    last_date = today
    end_of_week = last_date + dt.timedelta(days=(5 - last_date.weekday()) % 7)
    start_date = end_of_week - dt.timedelta(days=weeks * 7 - 1)
    by_date = {day["date"]: day for day in days}
    cells = []
    month_labels = []
    previous_month = None
    for week in range(weeks):
        week_start = start_date + dt.timedelta(days=week * 7)
        if week_start.month != previous_month and week < weeks - 1:
            label_date = week_start if week_start.day <= 7 or week == 0 else None
            if label_date:
                month_labels.append(text(grid_x + week * (cell + gap), grid_y - 12, label_date.strftime("%b"), 11, palette["faint"], 500, "mono"))
            previous_month = week_start.month
        for weekday in range(7):
            date = week_start + dt.timedelta(days=weekday)
            x = grid_x + week * (cell + gap)
            y = grid_y + weekday * (cell + gap)
            if date > last_date:
                cells.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="4" stroke="{palette["line"]}" stroke-dasharray="2 2"/>')
                continue
            day = by_date.get(date.isoformat(), {"count": 0, "level": 0})
            fill = palette["heat"][day["level"]]
            delay = 0.2 + (week + weekday) * 0.018
            # A slow diagonal wave passes over the grid after it has popped in
            wave = 2 + (week + weekday) * 0.06
            cells.append(
                f'<rect class="cell" style="animation-delay:{delay:.2f}s,{wave:.2f}s" x="{x}" y="{y}" width="{cell}" height="{cell}" rx="4" fill="{fill}">'
                f'<title>{date.isoformat()}: {day["count"]}</title></rect>'
            )
            if date == last_date:
                cells.append(
                    f'<rect class="ping" x="{x}" y="{y}" width="{cell}" height="{cell}" rx="4" stroke="{palette["accent"]}" stroke-width="1.5"/>'
                )
    parts.extend(month_labels)
    parts.extend(cells)

    legend_y = grid_y + 7 * (cell + gap) + 18
    legend_x = grid_x + grid_width - 5 * (cell + gap) + gap - 40
    legend = text(legend_x - 10, legend_y + 11, "Less", 11, palette["faint"], 500, "mono", anchor="end")
    for level in range(5):
        legend += f'<rect x="{legend_x + level * (cell + gap)}" y="{legend_y}" width="{cell}" height="{cell}" rx="4" fill="{palette["heat"][level]}"/>'
    legend += text(legend_x + 5 * (cell + gap) + 6, legend_y + 11, "More", 11, palette["faint"], 500, "mono")
    parts.append(rise(legend, 0.5))
    parts.append(text(WIDTH - 40, 58, copy["updated"], 11.5, palette["faint"], 500, "mono", 0.04, anchor="end"))

    height = max(legend_y + cell + 40, 316)
    title = f'{activity["total"]} {copy["contributions"]}, {first_tile[0].lower()} {first_tile[1]}, longest streak {longest}'
    extra_css = (
        f".cell{{transform-box:fill-box;transform-origin:center;animation:spring .7s {SPRING} both,glint 7s ease-in-out infinite}}"
        "@keyframes glint{0%,10%,100%{opacity:1}5%{opacity:.35}}"
    )
    return document(WIDTH, height, "".join(parts), theme, title, extra_css)


def render_working(theme):
    palette = THEMES[theme]
    copy = PROFILE["working"]
    parts = [rise(text(40, 66, copy["title"], 34, palette["text"], 700, tracking=-0.03), 0.05)]
    body, last_y = paragraph(40, 102, copy["text"], 17, WIDTH - 80, 26, palette["muted"])
    parts.append(rise(body, 0.1))

    tile_y = last_y + 30
    tile_gap = 12
    tile_width = (WIDTH - 80 - tile_gap * 2) / 3
    tile_height = 128
    steps = len(copy["steps"])
    period = 2.6 * steps + 1.2
    segment_css = []
    for index, step in enumerate(copy["steps"]):
        x = 40 + index * (tile_width + tile_gap)
        lines, _ = paragraph(x + 20, tile_y + 82, step, 15, tile_width - 40, 21, palette["text"], 500)
        # Progress segments fill one after another, like stories, to show the order of the steps
        start = index * 2.6 / period * 100
        end = (index + 1) * 2.6 / period * 100
        segment_css.append(
            f"@keyframes seg{index}{{0%,{start:.1f}%{{transform:scaleX(0)}}{end:.1f}%,94%{{transform:scaleX(1)}}100%{{transform:scaleX(0)}}}}"
            f".seg{index}{{transform-box:fill-box;transform-origin:left center;animation:seg{index} {period:.1f}s linear infinite}}"
        )
        segment_width = tile_width - 40
        tile = (
            f'<rect x="{x:.1f}" y="{tile_y:.1f}" width="{tile_width:.1f}" height="{tile_height}" rx="18" fill="{palette["tile"]}"/>'
            f'<rect x="{x + 20:.1f}" y="{tile_y + 20:.1f}" width="{segment_width:.1f}" height="3" rx="1.5" fill="{palette["line"]}"/>'
            f'<rect class="seg{index}" x="{x + 20:.1f}" y="{tile_y + 20:.1f}" width="{segment_width:.1f}" height="3" rx="1.5" fill="{palette["accent"]}"/>'
            + text(x + 20, tile_y + 52, f"0{index + 1}", 13, palette["accent"], 600, "mono", 0.06)
            + lines
        )
        parts.append(rise(tile, 0.16 + index * 0.08))

    button_y = tile_y + tile_height + 24
    button_width = 16 + 18 + 10 + text_width(copy["button"], 15, 600) + 22
    button = (
        f'<rect x="40" y="{button_y:.1f}" width="{button_width:.1f}" height="46" rx="23" fill="{palette["accent"]}"/>'
        + icon("ms-mail", 56, button_y + 14, 18, palette["accentText"])
        + text(84, button_y + 28.5, copy["button"], 15, palette["accentText"], 600)
    )
    parts.append(rise(button, 0.42))
    signature, signature_css = render_signature(WIDTH - 48, button_y + 44, 64, palette["text"])
    parts.append(signature)
    height = round(button_y + 46 + 40)
    title = f'{copy["title"]}. {copy["text"]} ' + " ".join(f"{index + 1}. {step}." for index, step in enumerate(copy["steps"]))
    return document(WIDTH, height, "".join(parts), theme, title, "".join(segment_css) + signature_css)


def render_signature(right, bottom, height, color):
    """Handwritten "Denys" drawn stroke by stroke, then held, then redrawn, like a pen signing."""
    left_x, top_y, right_x, bottom_y = SIGNATURE["box"]
    scale = height / (bottom_y - top_y)
    x = right - (right_x - left_x) * scale
    y = bottom - height
    total = sum(stroke["length"] for stroke in SIGNATURE["strokes"])
    draw = 2.6
    period = 11.0
    paths = []
    css = []
    elapsed = 0.6
    for index, stroke in enumerate(SIGNATURE["strokes"]):
        duration = draw * stroke["length"] / total
        start = elapsed / period * 100
        end = (elapsed + duration) / period * 100
        css.append(f"@keyframes pen{index}{{0%,{start:.2f}%{{stroke-dashoffset:1}}{end:.2f}%,100%{{stroke-dashoffset:0}}}}")
        css.append(f".pen{index}{{animation:pen{index} {period}s linear infinite}}")
        paths.append(
            f'<path class="pen{index}" d="{stroke["d"]}" pathLength="1" stroke-dasharray="1 1" stroke-dashoffset="0" '
            f'stroke="{color}" stroke-width="{2.2 / scale:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
        )
        elapsed += duration
    css.append(f".signature{{animation:signature {period}s linear infinite}}")
    css.append("@keyframes signature{0%,90%{opacity:1}97%,100%{opacity:0}}")
    group = (
        f'<g class="signature"><g transform="translate({x - left_x * scale:.1f} {y - top_y * scale:.1f}) scale({scale:.4f})">'
        + "".join(paths)
        + "</g></g>"
    )
    return group, "".join(css)


# README

def picture(name, alt, width="100%"):
    return (
        f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
        f'<img src="assets/{name}-light.svg" width="{width}" alt="{escape(alt, {chr(34): "&quot;"})}"></picture>'
    )


def linked(url, content):
    return f'<a href="{url}">{content}</a>'


def render_readme():
    hero = PROFILE["hero"]
    total_links = sum(link_width(link) for link in PROFILE["links"])
    scale = min(1.0, WIDTH / total_links)
    links = "".join(
        linked(link["url"], picture(f"link-{index}", link["label"], f"{link_width(link) * scale / WIDTH * 100:.2f}%"))
        for index, link in enumerate(PROFILE["links"])
    )
    featured = PROFILE["featured"]
    pair_rows = []
    for pair in PROFILE["pairs"]:
        cells = [linked(project["url"], picture(f'project-{project["id"]}', f'{project["title"]}: {project["text"]}', "49.9%")) for project in pair]
        pair_rows.append("".join(cells))
    shipped = PROFILE["sections"]["shipped"]
    building = PROFILE["sections"]["building"]
    zvukpad = PROFILE["zvukpad"]
    inkey = PROFILE["inkey"]
    working = PROFILE["working"]

    blocks = [
        '<div align="center">',
        picture("hero", f'{hero["name"]}. {hero["eyebrow"]}. {hero["subtitle"]}'),
        links,
        picture("now", PROFILE["now"]["title"] + ": " + "; ".join(item["label"] for item in PROFILE["now"]["items"])),
        picture("voice", ""),
        picture("section-shipped", f'{shipped["title"]}. {shipped["note"]}'),
        linked(featured["url"], picture("project-voice", f'{featured["title"]}: {featured["text"]}')),
        *pair_rows,
        picture("section-building", f'{building["title"]}. {building["note"]}'),
        picture("project-zvukpad", f'{zvukpad["title"]} ({zvukpad["status"].lower()}): {zvukpad["text"]}'),
        linked(inkey["url"], picture("project-inkey", f'{inkey["title"]}: {inkey["text"]}')),
        picture("stack", "Stack: " + ", ".join(label for group in PROFILE["stack"]["groups"] for _, label in group["items"])),
        picture("activity", "GitHub activity: contributions in the last year and streaks"),
        linked(working["url"], picture("working", f'{working["title"]}. {working["text"]} Email {working["button"]}')),
        '<sub>The cards are SVG, generated by <a href="scripts/build.py">scripts/build.py</a> from <a href="profile.json">profile.json</a>. Activity refreshes every hour.</sub>',
        "</div>",
    ]
    return "\n\n".join(blocks) + "\n"


def main():
    activity = fetch_activity()
    pair_height = 568
    for theme in THEMES:
        cards = {
            "hero": render_hero(theme),
            "now": render_now(theme),
            "voice": render_voice(theme),
            "section-shipped": render_section(PROFILE["sections"]["shipped"], theme),
            "section-building": render_section(PROFILE["sections"]["building"], theme),
            "project-voice": render_featured(theme),
            "project-zvukpad": render_zvukpad(theme),
            "project-inkey": render_inkey(theme),
            "stack": render_stack(theme),
            "activity": render_activity(theme, activity),
            "working": render_working(theme),
        }
        for index, link in enumerate(PROFILE["links"]):
            cards[f"link-{index}"] = render_link(link, index, theme)
        for pair in PROFILE["pairs"]:
            for side, project in enumerate(pair):
                cards[f'project-{project["id"]}'] = render_pair_card(project, theme, pair_height, side)
        for name, svg in cards.items():
            (OUT / f"{name}-{theme}.svg").write_text(svg)
    (ROOT / "README.md").write_text(render_readme())


if __name__ == "__main__":
    main()
