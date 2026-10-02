#!/usr/bin/env python3
"""
Generates the custom SVG artwork for the FilipTw GitHub profile README.

Every piece of text is converted to vector outlines, so the artwork looks the
same everywhere (GitHub does not let SVG images load web fonts).

    pip install fonttools uharfbuzz brotli
    python build.py

Fonts (Syne, JetBrains Mono, both OFL) are downloaded once from npm into .fonts/.
Edit CONFIG below and run the script again to regenerate assets/.
"""
import builtins
import html
import io
import keyword
import tarfile
import tokenize
import urllib.request
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

# ──────────────────────────────────────────────────────────────────────────
#  CONFIG — edit me
# ──────────────────────────────────────────────────────────────────────────
CONFIG = {
    "username": "FilipTw",
    "name": "Filip",
    "role": "Full-stack & AI developer",
    "tagline": ["I build backends, train models", "and ship the interfaces in between."],
    "marquee": [
        "Python", "Django", "FastAPI", "PyTorch", "TensorFlow", "TypeScript",
        "React", "Next.js", "Node.js", "PostgreSQL", "Redis", "RabbitMQ",
        "Docker", "AWS", "Prometheus",
    ],
    "code_file": "filip.py",
    "code": '''class Filip:
    """Full-stack & AI developer."""

    def __init__(self):
        self.username = "FilipTw"
        self.focus = ["Backends", "ML products", "Clean UIs"]
        self.daily = ["Python", "TypeScript", "Docker"]
        self.learning = "Always something new"

    def say_hi(self) -> str:
        return "Thanks for stopping by. Let's build something great!"
''',
    "stack": [
        ("Languages", ["Python", "TypeScript", "JavaScript", "HTML"]),
        ("Backend", ["Django", "FastAPI", "Node.js"]),
        ("AI & ML", ["PyTorch", "TensorFlow"]),
        ("Frontend", ["React", "Next.js", "Tailwind CSS"]),
        ("Data", ["PostgreSQL", "Redis", "RabbitMQ"]),
        ("Cloud & DevOps", ["AWS", "Docker", "GitHub Actions", "Linux"]),
        ("Monitoring", ["Sentry", "Prometheus"]),
        ("Workflow", ["Git", "GitHub", "GitLab", "Postman"]),
        ("Editors & notes", ["PyCharm", "WebStorm", "Notion"]),
    ],
    "sections": {
        "about": ("About", "A short introduction, in Python"),
        "stack": ("Stack", "What I build and ship with"),
        "activity": ("Activity", "Live numbers from GitHub"),
        "connect": ("Connect", "The fastest way to reach me"),
    },
    "cta": ["Let\u2019s build", "something."],
    "cta_button": "Send an email",
}

# ──────────────────────────────────────────────────────────────────────────
#  Design tokens
# ──────────────────────────────────────────────────────────────────────────
DARK = {
    "card": "#0D1F33", "line": "#1F3A57", "text": "#EAF0F6", "muted": "#8AA0B8",
    "blue": "#6FA8DC", "gold": "#FFD43B", "gold_text": "#FFD43B", "ghost": "#2A4A6E",
}
LIGHT = {
    "card": "#F2F5F8", "line": "#D3DCE6", "text": "#0D1F33", "muted": "#5A6E85",
    "blue": "#2F6797", "gold": "#FFD43B", "gold_text": "#8A6300", "ghost": "#C9D5E1",
}
W = 1200
M = 48

WANTED = {
    "syne-latin-800-normal.woff2", "syne-latin-700-normal.woff2",
    "syne-latin-600-normal.woff2", "jetbrains-mono-latin-400-normal.woff2",
}
ROOT = Path(__file__).resolve().parent
FONT_DIR = ROOT / ".fonts"
OUT = ROOT / "assets"

FONTS = {
    "display": ("@fontsource/syne", "5.3.0", "syne-latin-800-normal.woff2"),
    "bold": ("@fontsource/syne", "5.3.0", "syne-latin-700-normal.woff2"),
    "label": ("@fontsource/syne", "5.3.0", "syne-latin-600-normal.woff2"),
    "mono": ("@fontsource/jetbrains-mono", "5.3.0", "jetbrains-mono-latin-400-normal.woff2"),
}


# ──────────────────────────────────────────────────────────────────────────
#  Fonts → outlines
# ──────────────────────────────────────────────────────────────────────────
def fetch_font(pkg, version, filename):
    FONT_DIR.mkdir(exist_ok=True)
    target = FONT_DIR / filename
    if target.exists():
        return target
    short = pkg.split("/")[-1]
    url = f"https://registry.npmjs.org/{pkg}/-/{short}-{version}.tgz"
    print(f"  downloading {pkg}@{version}")
    data = urllib.request.urlopen(url).read()
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if Path(member.name).name in WANTED:
                (FONT_DIR / Path(member.name).name).write_bytes(tar.extractfile(member).read())
    return target


class Font:
    def __init__(self, key, path):
        self.key = key
        self.tt = TTFont(path)
        self.tt.flavor = None
        buf = io.BytesIO()
        self.tt.save(buf)
        self.hb = hb.Font(hb.Face(buf.getvalue()))
        self.upem = self.tt["head"].unitsPerEm
        self.glyphs = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()

    def shape(self, text):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "liga": True})
        return [(self.order[i.codepoint], p.x_advance, p.x_offset, p.y_offset)
                for i, p in zip(buf.glyph_infos, buf.glyph_positions)]

    def outline(self, glyph):
        pen = SVGPathPen(self.glyphs)
        self.glyphs[glyph].draw(pen)
        return pen.getCommands()


class Canvas:
    """Collects glyph outlines once per file and places them with <use>."""

    def __init__(self):
        self.defs = {}

    def gid(self, font, glyph):
        key = f"{font.key}-{glyph}".replace(".", "_")
        if key not in self.defs:
            self.defs[key] = font.outline(glyph)
        return key

    def measure(self, font, text, size, tracking=0.0):
        s = size / font.upem
        run = font.shape(text)
        return sum(a for _, a, _, _ in run) * s + tracking * size * max(len(run) - 1, 0)

    def glyph_runs(self, font, text, x, y, size, tracking=0.0, anchor="start"):
        s = size / font.upem
        if anchor != "start":
            w = self.measure(font, text, size, tracking)
            x -= w if anchor == "end" else w / 2
        out, pen_x = [], x
        for glyph, adv, dx, dy in font.shape(text):
            if self.defs.get(self.gid(font, glyph)):
                gx, gy = pen_x + dx * s, y - dy * s
                out.append((glyph, gx, gy, s))
            pen_x += adv * s + tracking * size
        return out

    def text(self, font, text, x, y, size, fill=None, stroke=None, sw=1.2,
             tracking=0.0, anchor="start", attrs=""):
        parts = []
        for glyph, gx, gy, s in self.glyph_runs(font, text, x, y, size, tracking, anchor):
            parts.append(f'<use href="#{self.gid(font, glyph)}" '
                         f'transform="translate({gx:.2f} {gy:.2f}) scale({s:.5f} {-s:.5f})"/>')
        paint = f'fill="{fill}"' if fill else 'fill="none"'
        if stroke:
            paint += f' stroke="{stroke}" stroke-width="{sw / (size / 1000):.1f}"'
        return f'<g {paint} {attrs}>{"".join(parts)}</g>'

    def defs_xml(self):
        return "".join(f'<path id="{k}" d="{d}"/>' for k, d in self.defs.items() if d)


def svg(width, height, body, canvas, style="", extra_defs="", label=""):
    label = html.escape(label)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="{label}">'
        f'<title>{label}</title>'
        f'<defs>{canvas.defs_xml()}{extra_defs}'
        f'{f"<style>{style}</style>" if style else ""}</defs>{body}</svg>'
    )


# ──────────────────────────────────────────────────────────────────────────
#  Pieces
# ──────────────────────────────────────────────────────────────────────────
def star(cx, cy, r, fill):
    """Six-point asterisk used as the marquee separator."""
    arms = []
    for i in range(3):
        arms.append(f'<rect x="{-r * 0.16:.2f}" y="{-r:.2f}" width="{r * 0.32:.2f}" '
                    f'height="{2 * r:.2f}" rx="{r * 0.16:.2f}" transform="rotate({i * 60})"/>')
    return f'<g fill="{fill}" transform="translate({cx:.2f} {cy:.2f})">{"".join(arms)}</g>'


def build_hero(F):
    c = Canvas()
    t = DARK
    H = 640
    strip_top = 552
    body = []

    body.append(f'<rect width="{W}" height="{H}" fill="{t["card"]}"/>')
    body.append(f'<circle cx="{W - 140}" cy="120" r="420" fill="url(#glow)"/>')

    # Top row
    body.append(c.text(F["label"], CONFIG["role"], M, 62, 19, fill=t["text"]))
    body.append(c.text(F["label"], f'github.com/{CONFIG["username"]}', W - M, 62, 19,
                       fill=t["muted"], anchor="end"))
    body.append(f'<rect x="{M}" y="92" width="{W - 2 * M}" height="1" fill="{t["line"]}"/>')

    # Tagline
    tag = "".join(
        c.text(F["label"], line, M, 146 + i * 36, 27, fill=t["text"])
        for i, line in enumerate(CONFIG["tagline"]))
    body.append(f'<g class="fade">{tag}</g>')

    # Marquee strip (drawn before the name so the name overlaps it)
    body.append(f'<rect x="0" y="{strip_top}" width="{W}" height="{H - strip_top}" fill="#0A1929"/>')
    body.append(f'<rect x="0" y="{strip_top}" width="{W}" height="1" fill="{t["line"]}"/>')
    size, base = 34, strip_top + 56
    items, x = [], 0.0
    gap = 34
    for i, word in enumerate(CONFIG["marquee"]):
        outlined = i % 2 == 1
        items.append(c.text(F["bold"], word, x, base, size,
                            fill=None if outlined else t["text"],
                            stroke=t["text"] if outlined else None, sw=1.1))
        x += c.measure(F["bold"], word, size) + gap
        items.append(star(x, base - size * 0.34, 9, t["gold"]))
        x += gap
    loop = x
    track = "".join(items)
    body.append(f'<g class="track"><g>{track}</g><g transform="translate({loop:.2f} 0)">{track}</g></g>')

    # Giant name, letter by letter
    name = CONFIG["name"]
    tracking = -0.035
    probe = c.measure(F["display"], name, 1000, tracking)
    nsize = (W - 2 * M + 10) / probe * 1000
    baseline = 515
    letters = c.glyph_runs(F["display"], name, M - 6, baseline, nsize, tracking)
    glyph_els = []
    for i, (glyph, gx, gy, s) in enumerate(letters):
        glyph_els.append(
            f'<g class="rise" style="animation-delay:{0.15 + i * 0.07:.2f}s">'
            f'<use href="#{c.gid(F["display"], glyph)}" '
            f'transform="translate({gx:.2f} {gy:.2f}) scale({s:.5f} {-s:.5f})"/></g>')
    body.append(f'<g clip-path="url(#reveal)" fill="{t["gold"]}">{"".join(glyph_els)}</g>')

    # Grain
    body.append(f'<rect width="{W}" height="{H}" filter="url(#grain)" opacity=".07"/>')

    extra = (
        f'<radialGradient id="glow"><stop offset="0" stop-color="#3776AB" stop-opacity=".32"/>'
        f'<stop offset="1" stop-color="#3776AB" stop-opacity="0"/></radialGradient>'
        f'<clipPath id="reveal"><rect x="0" y="93" width="{W}" height="{H - 93}"/></clipPath>'
        f'<clipPath id="card"><rect width="{W}" height="{H}" rx="28"/></clipPath>'
        '<filter id="grain" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="3" stitchTiles="stitch"/>'
        '<feColorMatrix values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 1 0 0 0 0"/></filter>'
    )
    style = (
        ".rise{animation:rise 1.25s cubic-bezier(.16,1,.3,1) both}"
        f"@keyframes rise{{from{{transform:translateY({H - 93}px)}}to{{transform:none}}}}"
        ".fade{animation:fade 1s cubic-bezier(.16,1,.3,1) .75s both}"
        "@keyframes fade{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}"
        f".track{{animation:slide {loop / 38:.1f}s linear infinite}}"
        f"@keyframes slide{{to{{transform:translateX(-{loop:.2f}px)}}}}"
        "@media (prefers-reduced-motion:reduce){.rise,.fade,.track{animation:none}}"
    )
    wrapped = f'<g clip-path="url(#card)">{"".join(body)}</g>'
    return svg(W, H, wrapped, c, style, extra, f'{CONFIG["name"]}, {CONFIG["role"]}')


def build_header(F, t, key):
    c = Canvas()
    H = 132
    title, desc = CONFIG["sections"][key]
    body = [
        c.text(F["display"], title, 0, 92, 62, fill=t["text"], tracking=-0.02),
        c.text(F["label"], desc, W, 92, 20, fill=t["muted"], anchor="end"),
        f'<rect x="0" y="118" width="{W}" height="1" fill="{t["line"]}"/>',
        f'<rect x="0" y="116" width="72" height="4" fill="{t["gold"]}"/>',
    ]
    return svg(W, H, "".join(body), c, label=title)


def tokenize_python(src):
    kinds = []
    prev_name = None
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.NAME:
            if prev_name in ("class", "def"):
                kind = "def"
            elif keyword.iskeyword(tok.string):
                kind = "kw"
            elif tok.string == "self":
                kind = "self"
            elif tok.string in dir(builtins):
                kind = "builtin"
            else:
                kind = "name"
            prev_name = tok.string
        elif tok.type == tokenize.STRING:
            kind = "doc" if tok.string.startswith('"""') else "str"
        elif tok.type == tokenize.COMMENT:
            kind = "doc"
        elif tok.type == tokenize.OP:
            kind = "op"
        else:
            continue
        kinds.append((tok.start, tok.string, kind))
    return kinds


def build_about(F, t):
    c = Canvas()
    lines = CONFIG["code"].rstrip("\n").split("\n")
    size, lh = 21, 37
    top = 64
    pad_top = 44
    H = top + pad_top + lh * (len(lines) + 1) + 20
    adv = 600 / 1000 * size
    code_x = M + 72
    colors = {"kw": t["blue"], "def": t["gold_text"], "self": t["muted"], "builtin": t["blue"],
              "name": t["text"], "str": t["gold_text"], "doc": t["muted"], "op": t["muted"]}

    body = [
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="24" fill="{t["card"]}" stroke="{t["line"]}"/>',
        f'<rect x="1" y="{top}" width="{W - 2}" height="1" fill="{t["line"]}"/>',
        f'<rect x="{M}" y="26" width="12" height="12" rx="2" fill="{t["gold"]}"/>',
        c.text(F["label"], CONFIG["code_file"], M + 24, 38, 18, fill=t["text"]),
        c.text(F["label"], f'{len(lines)} lines', W - M, 38, 18, fill=t["muted"], anchor="end"),
    ]
    for i in range(len(lines)):
        y = top + pad_top + i * lh + size * 0.72
        body.append(c.text(F["mono"], str(i + 1), M + 34, y, size, fill=t["ghost"], anchor="end"))
    for (row, col), string, kind in tokenize_python(CONFIG["code"]):
        y = top + pad_top + (row - 1) * lh + size * 0.72
        body.append(c.text(F["mono"], string, code_x + col * adv, y, size, fill=colors[kind]))
    cursor_y = top + pad_top + len(lines) * lh
    body.append(f'<rect class="blink" x="{code_x + 4 * adv:.2f}" y="{cursor_y + 2}" '
                f'width="{adv:.2f}" height="{size + 4}" fill="{t["gold"]}"/>')
    style = (".blink{animation:blink 1.1s steps(1) infinite}"
             "@keyframes blink{50%{opacity:0}}"
             "@media (prefers-reduced-motion:reduce){.blink{animation:none}}")
    return svg(W, H, "".join(body), c, style, label=f'About {CONFIG["name"]}')


def build_stack(F, t):
    c = Canvas()
    rows = CONFIG["stack"]
    rh = 74
    H = rh * len(rows) + 16
    col_x = 360
    body = [f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="24" fill="{t["card"]}" stroke="{t["line"]}"/>']
    for i, (cat, items) in enumerate(rows):
        y0 = 8 + i * rh
        base = y0 + rh / 2 + 9
        body.append(c.text(F["label"], cat, M, base - 1, 19, fill=t["muted"]))
        size = 27
        sep = "  /  "
        full = sep.join(items)
        while c.measure(F["bold"], full, size) > W - M - col_x and size > 18:
            size -= 1
        x = col_x
        for j, item in enumerate(items):
            body.append(c.text(F["bold"], item, x, base, size, fill=t["text"]))
            x += c.measure(F["bold"], item, size)
            if j < len(items) - 1:
                gap = c.measure(F["bold"], "  ", size)
                body.append(c.text(F["bold"], "/", x + gap, base, size, fill=t["ghost"]))
                x += c.measure(F["bold"], sep, size)
        if i < len(rows) - 1:
            body.append(f'<rect x="{M}" y="{y0 + rh}" width="{W - 2 * M}" height="1" fill="{t["line"]}"/>')
    return svg(W, H, "".join(body), c, label="Tech stack")


def build_cta(F, t):
    c = Canvas()
    H = 440
    l1, l2 = CONFIG["cta"]
    size = 116
    body = [f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="24" fill="{t["card"]}" stroke="{t["line"]}"/>']
    body.append(c.text(F["display"], l1, M - 4, 156, size, fill=t["text"], tracking=-0.03))
    body.append(c.text(F["display"], l2, M - 4, 282, size, fill=t["text"], tracking=-0.03))
    label = CONFIG["cta_button"]
    bw, bh = c.measure(F["bold"], label, 22) + 72, 66
    bx, by = M, 334
    body.append(f'<rect x="{bx}" y="{by}" width="{bw:.2f}" height="{bh}" rx="{bh / 2}" fill="{t["gold"]}"/>')
    body.append(c.text(F["bold"], label, bx + bw / 2, by + bh / 2 + 8, 22, fill="#0D1F33", anchor="middle"))
    body.append(c.text(F["label"], "Opens your mail app", bx + bw + 24, by + bh / 2 + 7, 19, fill=t["muted"]))
    return svg(W, H, "".join(body), c, label=f'{l1} {l2} {label}')


def build_footer(F, t):
    c = Canvas()
    H = 230
    word = CONFIG["username"]
    probe = c.measure(F["display"], word, 1000, -0.03)
    size = W / probe * 1000
    body = [c.text(F["display"], word, 0, H + size * 0.2, size, stroke=t["ghost"], sw=1.6, tracking=-0.03)]
    return svg(W, H, "".join(body), c, label=word)


# ──────────────────────────────────────────────────────────────────────────
def main():
    fonts = {k: Font(k, fetch_font(*v)) for k, v in FONTS.items()}
    OUT.mkdir(exist_ok=True)
    files = {"hero.svg": build_hero(fonts)}
    for theme_name, t in (("dark", DARK), ("light", LIGHT)):
        for key in CONFIG["sections"]:
            files[f"header-{key}-{theme_name}.svg"] = build_header(fonts, t, key)
        files[f"about-{theme_name}.svg"] = build_about(fonts, t)
        files[f"stack-{theme_name}.svg"] = build_stack(fonts, t)
        files[f"connect-{theme_name}.svg"] = build_cta(fonts, t)
        files[f"footer-{theme_name}.svg"] = build_footer(fonts, t)
    for name, data in files.items():
        (OUT / name).write_text(data, encoding="utf-8")
        print(f"  {name:28s} {len(data.encode()) / 1024:6.1f} KB")


if __name__ == "__main__":
    main()
