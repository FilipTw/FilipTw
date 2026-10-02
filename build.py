#!/usr/bin/env python3
"""
Artwork generator for the FilipTw GitHub profile.

    pip install fonttools uharfbuzz brotli numpy contourpy
    python build.py

Writes light and dark SVGs into assets/. Text is converted to outlines because
GitHub does not let SVG images load fonts. The GitHub Action in
.github/workflows/profile.yml runs this daily, so the Activity panel stays live
and any change to CONFIG is rebuilt automatically after you commit it.

Typefaces: Mona Sans and Monaspace Neon by GitHub (SIL Open Font License),
downloaded from npm into .fonts/ on first run.
"""
import datetime as dt
import hashlib
import html
import io
import json
import os
import re
import tarfile
import urllib.request
from pathlib import Path

import contourpy
import numpy as np
import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

# ════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════════════════════════════════
CONFIG = {
    "username": "FilipTw",
    "name": "Filip",
    "role": "Full-stack & AI developer",
    "tagline": "I build backends, train models and ship the interfaces in between.",
    "hero_caption": "Gradient descent on a toy loss surface",
    "about": (
        "I\u2019m Filip, a full-stack developer working where web software meets "
        "machine learning. I design APIs in Django and FastAPI, train models in "
        "PyTorch and build the React interfaces that put them in people\u2019s hands."
    ),
    "facts": [
        ("Focus", "Scalable backends, ML-powered products, clean interfaces"),
        ("Daily drivers", "Python, TypeScript, Docker"),
    ],
    "stack": [
        ("Languages", ["Python", "TypeScript", "JavaScript", "HTML"]),
        ("Backend", ["Django", "FastAPI", "Node.js"]),
        ("Machine learning", ["PyTorch", "TensorFlow"]),
        ("Frontend", ["React", "Next.js", "Tailwind CSS"]),
        ("Data & messaging", ["PostgreSQL", "Redis", "RabbitMQ"]),
        ("Cloud & DevOps", ["AWS", "Docker", "GitHub Actions", "Linux"]),
        ("Observability", ["Sentry", "Prometheus"]),
        ("Workflow", ["Git", "GitHub", "GitLab", "Postman"]),
        ("Editors & notes", ["PyCharm", "WebStorm", "Notion"]),
    ],
    "contact_line": "Let\u2019s build something together.",
    # (label, text shown, link). Replace the placeholders with your own.
    "links": [
        ("Email", "ft@gmail.com", "mailto:filip.twardawa@gmail.com"),
        ("LinkedIn", "linkedin.com/in/ft-profile", "https://www.linkedin.com"),
        ("GitHub", "github.com/FilipTw", "https://github.com/FilipTw"),
    ],
    # Selected work shows your pinned repositories (or the most starred ones).
    "work_limit": 4,
}

# ════════════════════════════════════════════════════════════════════════════
#  Design tokens
# ════════════════════════════════════════════════════════════════════════════
THEMES = {
    "light": {
        "page": "#FFFFFF", "ink": "#0A0B0D", "muted": "#676C75", "faint": "#A5AAB2",
        "line": "#E2E4E8", "contour": "#CDD1D8", "accent": "#2B3BFF", "cell": "#EEF0F3",
    },
    "dark": {
        "page": "#0D1117", "ink": "#EEF1F5", "muted": "#8C939D", "faint": "#565D67",
        "line": "#262C35", "contour": "#28303B", "accent": "#7D87FF", "cell": "#161B22",
    },
}
W = 1200          # every asset shares this width, so edges align in the README
COL = 300         # editorial grid: label column | content column
FONT_SOURCES = {
    "mona-sans-latin-wdth-normal.woff2": ("@fontsource-variable/mona-sans", "5.3.0"),
    "monaspace-neon-latin-400-normal.woff2": ("@fontsource/monaspace-neon", "5.3.0"),
}
ROOT = Path(__file__).resolve().parent
FONT_DIR, OUT = ROOT / ".fonts", ROOT / "assets"


# ════════════════════════════════════════════════════════════════════════════
#  Type engine: shape with HarfBuzz, draw outlines with fontTools
# ════════════════════════════════════════════════════════════════════════════
def font_file(name):
    FONT_DIR.mkdir(exist_ok=True)
    path = FONT_DIR / name
    if not path.exists():
        pkg, ver = FONT_SOURCES[name]
        url = f"https://registry.npmjs.org/{pkg}/-/{pkg.split('/')[-1]}-{ver}.tgz"
        print(f"  fetching {pkg}@{ver}")
        with tarfile.open(fileobj=io.BytesIO(urllib.request.urlopen(url).read())) as tar:
            path.write_bytes(tar.extractfile(f"package/files/{name}").read())
    return path


class Font:
    _raw = {}

    def __init__(self, key, file, location=None):
        path = font_file(file)
        if path not in Font._raw:
            tt = TTFont(path)
            tt.flavor = None
            buf = io.BytesIO()
            tt.save(buf)
            Font._raw[path] = (tt, buf.getvalue())
        self.tt, raw = Font._raw[path]
        self.key, self.location = key, location or {}
        self.hb = hb.Font(hb.Face(raw))
        if self.location:
            self.hb.set_variations(self.location)
        self.upem = self.tt["head"].unitsPerEm
        self.glyphs = self.tt.getGlyphSet(location=self.location or None)
        self.order = self.tt.getGlyphOrder()

    def shape(self, text):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "liga": True})
        return [(self.order[i.codepoint], p.x_advance, p.x_offset, p.y_offset)
                for i, p in zip(buf.glyph_infos, buf.glyph_positions)]

    def outline(self, glyph):
        pen = SVGPathPen(self.glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
        self.glyphs[glyph].draw(pen)
        return pen.getCommands()

    def lsb(self, text):
        """Left side bearing of the first glyph, for optical left alignment."""
        glyph = self.shape(text)[0][0]
        pen = BoundsPen(self.glyphs)
        self.glyphs[glyph].draw(pen)
        return pen.bounds[0] if pen.bounds else 0


class Canvas:
    def __init__(self):
        self.defs = {}
        self.extra = []
        self.css = []

    def gid(self, font, glyph):
        key = f"{font.key}-{glyph}".replace(".", "_")
        if key not in self.defs:
            self.defs[key] = font.outline(glyph)
        return key

    def measure(self, font, text, size, tracking=0.0):
        run = font.shape(text)
        return sum(r[1] for r in run) * size / font.upem + tracking * size * max(len(run) - 1, 0)

    def glyphs(self, font, text, x, y, size, tracking=0.0, anchor="start", optical=False):
        s = size / font.upem
        if anchor != "start":
            w = self.measure(font, text, size, tracking)
            x -= w if anchor == "end" else w / 2
        if optical:
            x -= font.lsb(text) * s
        out, pen = [], x
        for glyph, adv, dx, dy in font.shape(text):
            key = self.gid(font, glyph)
            if self.defs[key]:
                out.append((key, pen + dx * s, y - dy * s, s))
            pen += adv * s + tracking * size
        return out

    @staticmethod
    def use(key, x, y, s):
        return f'<use href="#{key}" transform="translate({x:.2f} {y:.2f}) scale({s:.5f} {-s:.5f})"/>'

    def text(self, font, text, x, y, size, fill, tracking=0.0, anchor="start",
             optical=False, attrs=""):
        inner = "".join(self.use(*g) for g in
                        self.glyphs(font, text, x, y, size, tracking, anchor, optical))
        return f'<g fill="{fill}"{attrs}>{inner}</g>'

    def wrap(self, font, text, size, width, tracking=0.0):
        lines, line = [], ""
        for word in text.split():
            trial = f"{line} {word}".strip()
            if line and self.measure(font, trial, size, tracking) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        return lines + [line] if line else lines

    def wrap_balanced(self, font, text, size, width, tracking=0.0):
        """Wrap, then narrow the measure until the last line is not a lone word."""
        lines, w = self.wrap(font, text, size, width, tracking), width
        while len(lines) > 1 and len(lines[-1].split()) < 2 and w > width * 0.75:
            w -= 8
            lines = self.wrap(font, text, size, w, tracking)
        return lines

    def fit(self, font, text, size, width):
        if self.measure(font, text, size) <= width:
            return text
        while text and self.measure(font, text + "\u2026", size) > width:
            text = text[:-1]
        return text.rstrip(" ,.;:") + "\u2026"

    def render(self, height, body, label):
        defs = "".join(f'<path id="{k}" d="{d}"/>' for k, d in self.defs.items() if d)
        style = f"<style>{''.join(self.css)}</style>" if self.css else ""
        label = html.escape(label)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" '
                f'width="{W}" height="{height}" role="img" aria-label="{label}">'
                f'<title>{label}</title><defs>{defs}{"".join(self.extra)}{style}</defs>'
                f'{body}</svg>')


def mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


def fonts():
    mona = "mona-sans-latin-wdth-normal.woff2"
    return {
        "display": Font("d", mona, {"wdth": 125, "wght": 300}),
        "text": Font("t", mona, {"wdth": 100, "wght": 420}),
        "medium": Font("m", mona, {"wdth": 100, "wght": 540}),
        "mono": Font("c", "monaspace-neon-latin-400-normal.woff2"),
    }


# ════════════════════════════════════════════════════════════════════════════
#  Hero: gradient descent on a loss surface
# ════════════════════════════════════════════════════════════════════════════
HERO_H = 760
TARGET = (845.0, 262.0)


def loss(x, y):
    x, y = np.asarray(x, float) / 1000, np.asarray(y, float) / 1000
    gx, gy = TARGET[0] / 1000, TARGET[1] / 1000
    u, v = (x - gx) / 0.20, (y - gy) / 0.11
    f = -1.00 * np.exp(-(u * u + v * v - 0.9 * u * v))
    f -= 0.55 * np.exp(-(((x - 0.30) / 0.17) ** 2 + ((y - 0.52) / 0.14) ** 2))
    f -= 0.30 * np.exp(-(((x - 0.62) / 0.10) ** 2 + ((y - 0.62) / 0.10) ** 2))
    f += 0.55 * ((x - 0.70) ** 2 + 1.2 * (y - 0.32) ** 2)
    f += 0.035 * np.sin(11 * x + 1.3) * np.cos(9 * y + 0.4)
    return f


def descent(start=(110.0, 128.0), lr=2500.0, beta=0.88, steps=220, h=0.5):
    p, vel, pts = np.array(start), np.zeros(2), [np.array(start)]
    for _ in range(steps):
        g = np.array([(loss(p[0] + h, p[1]) - loss(p[0] - h, p[1])) / (2 * h),
                      (loss(p[0], p[1] + h) - loss(p[0], p[1] - h)) / (2 * h)])
        vel = beta * vel - lr * g
        p = p + vel
        pts.append(p.copy())
    pts = np.array(pts)
    moving = np.hypot(*np.diff(pts, axis=0).T) > 0.35
    last = len(moving) - int(np.argmax(moving[::-1]))
    return pts[: last + 1]


def smooth(pts, times, step=7.0):
    """Catmull-Rom resampling so the trail and the marker share one smooth curve."""
    out_p, out_t = [pts[0]], [times[0]]
    n = len(pts)
    for i in range(n - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, n - 1)]
        k = max(1, int(np.ceil(np.hypot(*(p2 - p1)) / step)))
        for j in range(1, k + 1):
            u = j / k
            q = 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u ** 2
                       + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)
            out_p.append(q)
            out_t.append(times[i] + (times[i + 1] - times[i]) * u)
    return np.array(out_p), out_t


def simplify(pts, eps):
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ab = b - a
    n = np.hypot(*ab)
    d = np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / n if n > 1e-9 \
        else np.hypot(*(pts - a).T)
    i = int(np.argmax(d))
    if d[i] > eps:
        return np.vstack([simplify(pts[: i + 1], eps)[:-1], simplify(pts[i:], eps)])
    return np.vstack([a, b])


def inside(poly, pt):
    x, y = pt
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, np.roll(poly, -1, axis=0)):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def contour_lines(levels=34, res=3.0, pad=40):
    xs, ys = np.arange(-pad, W + pad, res), np.arange(-pad, HERO_H + pad, res)
    X, Y = np.meshgrid(xs, ys)
    Z = loss(X, Y)
    gen = contourpy.contour_generator(X, Y, Z, line_type=contourpy.LineType.Separate)
    out = []
    for k, level in enumerate(np.linspace(Z.min() + 0.02, np.percentile(Z, 92), levels)):
        for line in gen.lines(level):
            if len(line) >= 6:
                line = simplify(line, 0.35)
                closed = np.allclose(line[0], line[-1])
                out.append((k, line, closed and inside(line, TARGET)))
    return out, float(Z.min())


def poly_d(pts):
    return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts)


def build_hero(F, t):
    c = Canvas()
    H = HERO_H
    lines, zmin = contour_lines()
    pts = descent()
    n = len(pts)
    t0, dur = 1.25, 3.6                        # descent start, duration (s)
    times = [t0 + dur * i / (n - 1) for i in range(n)]
    body = []

    # ── contour field ──────────────────────────────────────────────────────
    k_inner = max(k for k, _, hit in lines if hit) + 1
    paths = []
    for k, line, hit in lines:
        depth = 1 - k / k_inner
        tint = min(max((depth - 0.42) / 0.58, 0), 1) ** 1.3 if hit else 0
        if tint > 0:
            stroke = mix(t["contour"], t["accent"], 0.12 + 0.88 * tint)
            width = 1.1 + 0.4 * tint
        else:
            stroke, width = t["contour"], 1.1
        paths.append(f'<path class="ct" pathLength="1" style="animation-delay:{0.05 + k * 0.032:.3f}s" '
                     f'd="{poly_d(line)}" stroke="{stroke}" stroke-width="{width:.2f}"/>')
    body.append(f'<g fill="none" mask="url(#fade)">{"".join(paths)}</g>')
    c.extra.append(
        f'<radialGradient id="rad" gradientUnits="userSpaceOnUse" cx="790" cy="300" r="820">'
        f'<stop offset=".45" stop-color="#fff"/><stop offset="1" stop-color="#000"/></radialGradient>'
        f'<linearGradient id="vfade" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="{H}">'
        f'<stop offset="0" stop-opacity=".9"/><stop offset=".13" stop-opacity="0"/>'
        f'<stop offset=".5" stop-opacity="0"/><stop offset=".9" stop-opacity=".92"/></linearGradient>'
        f'<mask id="fade" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">'
        f'<rect width="{W}" height="{H}" fill="url(#rad)"/>'
        f'<rect width="{W}" height="{H}" fill="url(#vfade)"/></mask>')
    c.css.append(".ct{stroke-dasharray:1 1;animation:draw 2.2s cubic-bezier(.65,0,.35,1) both}"
                 "@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}")

    # ── descent trail and marker ───────────────────────────────────────────
    curve, ctimes = smooth(pts, times)
    seg = np.hypot(*np.diff(curve, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)]) / seg.sum()
    trail_kf = "".join(f"{(ti - t0) / dur * 100:.2f}%{{stroke-dashoffset:{1 - ci:.4f}}}"
                       for ti, ci in zip(ctimes, cum))
    move_kf = "".join(f"{(ti - t0) / dur * 100:.2f}%{{transform:translate({x:.1f}px,{y:.1f}px)}}"
                      for ti, (x, y) in zip(ctimes, curve))
    c.css.append(f".trail{{stroke-dasharray:1 1;animation:trail {dur}s linear {t0}s both}}"
                 f"@keyframes trail{{{trail_kf}}}"
                 f".dot{{animation:move {dur}s linear {t0}s both}}@keyframes move{{{move_kf}}}")
    sx, sy = pts[0]
    ex, ey = pts[-1]
    body.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="4.5" fill="none" stroke="{t["muted"]}" '
                f'stroke-width="1.4" class="fd" style="animation-delay:{t0 - 0.3}s"/>')
    body.append(f'<path class="trail" pathLength="1" d="{poly_d(curve)}" fill="none" stroke="{t["accent"]}" '
                f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>')
    body.append(
        f'<g class="dot" transform="translate({ex:.1f} {ey:.1f})">'
        f'<circle class="pulse" r="7" fill="none" stroke="{t["accent"]}" stroke-width="1.4"/>'
        f'<circle r="13" fill="{t["accent"]}" opacity=".16"/>'
        f'<circle r="6" fill="{t["accent"]}"/></g>')
    c.css.append(f".pulse{{transform-box:fill-box;transform-origin:center;"
                 f"animation:pulse 2.8s cubic-bezier(.2,.6,.3,1) {t0 + dur:.2f}s infinite both}}"
                 "@keyframes pulse{0%{transform:scale(1);opacity:.8}100%{transform:scale(4.2);opacity:0}}")
    lx, ly = ex + 150, ey - 112
    body.append(f'<g class="fd" style="animation-delay:{t0 + dur:.2f}s">'
                f'<path d="M{ex + 10:.1f} {ey - 10:.1f}L{lx - 40:.1f} {ly:.1f}H{lx - 8:.1f}" fill="none" '
                f'stroke="{t["muted"]}" stroke-width="1"/>'
                + c.text(F["mono"], "minimum", lx, ly + 5, 14, t["muted"]) + '</g>')
    body.append(c.text(F["mono"], "init", sx, sy + 30, 14, t["muted"], anchor="middle",
                       attrs=f' class="fd" style="animation-delay:{t0 - 0.3}s"'))

    # ── top row: caption + live readout ────────────────────────────────────
    body.append(c.text(F["text"], CONFIG["hero_caption"], 0, 38, 17, t["muted"],
                       attrs=' class="fd" style="animation-delay:.2s"'))
    ms = 16
    adv = c.measure(F["mono"], "0", ms)
    loss_scale = 2.4 / (loss(*pts[0]) - zmin)
    x_loss_val = W - 6 * adv
    x_loss_lab = x_loss_val - adv * 5.2
    x_ep_val = x_loss_lab - adv * 6.5
    x_ep_lab = x_ep_val - adv * 6.2
    readout = [c.text(F["mono"], "epoch", x_ep_lab, 38, ms, t["muted"]),
               c.text(F["mono"], "loss", x_loss_lab, 38, ms, t["muted"])]
    frames = list(range(0, n, 2))
    if frames[-1] != n - 1:
        frames.append(n - 1)
    for j, i in enumerate(frames):
        value = (loss(*pts[i]) - zmin) * loss_scale + 0.0021
        group = (c.text(F["mono"], f"{i:03d}", x_ep_val, 38, ms, t["ink"]) +
                 c.text(F["mono"], f"{value:.4f}", x_loss_val, 38, ms, t["ink"]))
        if j == len(frames) - 1:
            style = f"animation:off {times[i]:.3f}s step-end"
            readout.append(f'<g class="fr last" style="{style}">{group}</g>')
        else:
            start = 0 if j == 0 else times[i]
            end = times[frames[j + 1]]
            style = f"animation:on {end - start:.3f}s step-end {start:.3f}s"
            readout.append(f'<g class="fr" style="{style}">{group}</g>')
    body.append(f'<g class="fd" style="animation-delay:.2s">{"".join(readout)}</g>')
    c.css.append(".fr{opacity:0}.fr.last{opacity:1}"
                 "@keyframes on{0%,100%{opacity:1}}@keyframes off{0%,100%{opacity:0}}")

    # ── name, letter by letter ─────────────────────────────────────────────
    name = CONFIG["name"]
    track = -0.03
    size = 680 / c.measure(F["display"], name, 1000, track) * 1000
    base = 636
    cap = 0.729 * size
    letters = c.glyphs(F["display"], name, 0, base, size, track, optical=True)
    els = "".join(f'<g class="ch" style="animation-delay:{0.35 + i * 0.075:.3f}s">{c.use(*g)}</g>'
                  for i, g in enumerate(letters))
    top, bottom = base - cap - 40, base + 0.32 * size
    c.extra.append(f'<clipPath id="nm"><rect x="-20" y="{top:.0f}" width="{W + 40}" '
                   f'height="{bottom - top:.0f}"/></clipPath>')
    body.append(f'<g clip-path="url(#nm)" fill="{t["ink"]}">{els}</g>')
    c.css.append(".ch{animation:rise 1.4s cubic-bezier(.19,1,.22,1) both}"
                 f"@keyframes rise{{from{{transform:translateY({bottom - top:.0f}px)}}to{{transform:none}}}}")

    # ── role + tagline, bottom right ───────────────────────────────────────
    bx, bw = 812, W - 812
    tag = c.wrap(F["text"], CONFIG["tagline"], 19, bw)
    y_last = base
    block = [c.text(F["text"], line, bx, y_last - (len(tag) - 1 - i) * 27, 19, t["muted"])
             for i, line in enumerate(tag)]
    block.append(c.text(F["medium"], CONFIG["role"], bx, y_last - (len(tag) - 1) * 27 - 40, 23, t["ink"]))
    body.append(f'<g class="fd" style="animation-delay:.95s">{"".join(block)}</g>')

    c.css.append(".fd{animation:fd 1.3s cubic-bezier(.19,1,.22,1) both}"
                 "@keyframes fd{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}"
                 "@media (prefers-reduced-motion:reduce){.ct,.trail,.dot,.pulse,.ch,.fd,.fr{animation:none!important}}")
    return c.render(H, "".join(body), f'{name}, {CONFIG["role"]}. {CONFIG["tagline"]}')


# ════════════════════════════════════════════════════════════════════════════
#  Editorial sections
# ════════════════════════════════════════════════════════════════════════════
def section_head(c, F, t, label, right=None):
    out = [f'<rect x="0" y="0" width="{W}" height="1" fill="{t["line"]}"/>',
           c.text(F["text"], label, 0, 46, 17, t["muted"])]
    if right:
        out.append(c.text(F["text"], right, W, 46, 17, t["muted"], anchor="end"))
    return out


def build_about(F, t):
    c = Canvas()
    body = section_head(c, F, t, "About")
    size, lh = 38, 50
    lines = c.wrap_balanced(F["text"], CONFIG["about"], size, W - COL, -0.012)
    y = 46 - 0.729 * 17 + 0.729 * size
    for i, line in enumerate(lines):
        body.append(c.text(F["text"], line, COL, y + i * lh, size, t["ink"], -0.012, optical=True))
    y += (len(lines) - 1) * lh + 76
    colw = (W - COL) / len(CONFIG["facts"])
    for j, (label, value) in enumerate(CONFIG["facts"]):
        x = COL + j * colw
        body.append(c.text(F["text"], label, x, y, 17, t["muted"]))
        for k, line in enumerate(c.wrap(F["text"], value, 21, colw - 40)):
            body.append(c.text(F["text"], line, x, y + 34 + k * 29, 21, t["ink"]))
    return c.render(int(y + 34 + 29 * 2 + 20), "".join(body), "About. " + CONFIG["about"])


def build_stack(F, t):
    c = Canvas()
    body = section_head(c, F, t, "Stack")
    groups = CONFIG["stack"]
    cols = 3
    colw = (W - COL) / cols
    y0, lh = 46, 34
    row_h = []
    for r in range(0, len(groups), cols):
        tallest = max(len(items) for _, items in groups[r:r + cols])
        row_h.append(30 + tallest * lh + 46)
    y = y0
    for r, start in enumerate(range(0, len(groups), cols)):
        for j, (label, items) in enumerate(groups[start:start + cols]):
            x = COL + j * colw
            body.append(c.text(F["text"], label, x, y, 17, t["muted"]))
            for k, item in enumerate(items):
                body.append(c.text(F["text"], item, x, y + 40 + k * lh, 24, t["ink"], -0.01))
        y += row_h[r]
    label = "Stack. " + ". ".join(f"{g}: {', '.join(i)}" for g, i in groups)
    return c.render(int(y - 30), "".join(body), label)


def build_contact(F, t):
    c = Canvas()
    body = section_head(c, F, t, "Contact")
    size = 58
    lines = c.wrap_balanced(F["display"], CONFIG["contact_line"], size, W - COL, -0.03)
    y = 46 - 0.729 * 17 + 0.729 * size
    for i, line in enumerate(lines):
        body.append(c.text(F["display"], line, COL, y + i * 70, size, t["ink"], -0.03, optical=True))
    return c.render(int(y + (len(lines) - 1) * 70 + 56), "".join(body), CONFIG["contact_line"])


def build_link_row(F, t, label, value, last=False):
    c = Canvas()
    H = 78
    body = [f'<rect x="{COL}" y="0" width="{W - COL}" height="1" fill="{t["line"]}"/>',
            c.text(F["text"], label, COL, 47, 17, t["muted"]),
            c.text(F["text"], value, COL + 300, 48, 24, t["accent"], -0.01)]
    if last:
        body.append(f'<rect x="{COL}" y="{H - 1}" width="{W - COL}" height="1" fill="{t["line"]}"/>')
    return c.render(H, "".join(body), f"{label}: {value}")


def build_work_row(F, t, repo, head=False, last=False):
    c = Canvas()
    H = 112
    body = []
    if head:
        body += [f'<rect x="0" y="0" width="{W}" height="1" fill="{t["line"]}"/>',
                 c.text(F["text"], "Selected work", 0, 46, 17, t["muted"])]
    else:
        body.append(f'<rect x="{COL}" y="0" width="{W - COL}" height="1" fill="{t["line"]}"/>')
    body.append(c.text(F["display"], repo["name"], COL, 56, 34, t["ink"], -0.02, optical=True))
    desc = c.fit(F["text"], repo.get("description") or "No description yet", 18, 620)
    body.append(c.text(F["text"], desc, COL, 90, 18, t["muted"]))
    if repo.get("language"):
        body.append(c.text(F["mono"], repo["language"], W, 52, 15, t["muted"], anchor="end"))
    stars = repo.get("stars", 0)
    body.append(c.text(F["mono"], f'{stars} star{"" if stars == 1 else "s"}', W, 88, 15, t["muted"], anchor="end"))
    if last:
        body.append(f'<rect x="{COL}" y="{H - 1}" width="{W - COL}" height="1" fill="{t["line"]}"/>')
    return c.render(H, "".join(body), f'{repo["name"]}. {repo.get("description") or ""}')


def build_colophon(F, t, today):
    c = Canvas()
    body = [f'<rect x="0" y="0" width="{W}" height="1" fill="{t["line"]}"/>',
            c.text(F["text"], f'{CONFIG["name"]}, {today.year}', 0, 46, 16, t["muted"]),
            c.text(F["text"], "Set in Mona Sans and Monaspace Neon. Artwork generated with Python.",
                   W, 46, 16, t["muted"], anchor="end")]
    return c.render(70, "".join(body), f'{CONFIG["name"]}, {today.year}')


# ════════════════════════════════════════════════════════════════════════════
#  Activity: live data from GitHub
# ════════════════════════════════════════════════════════════════════════════
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
REPO_FIELDS = "name description url stargazerCount primaryLanguage{name}"
QUERY = """query($login:String!){user(login:$login){
  followers{totalCount}
  pinnedItems(first:6,types:REPOSITORY){nodes{...on Repository{%s}}}
  repositories(ownerAffiliations:OWNER,privacy:PUBLIC,isFork:false,first:100,
               orderBy:{field:STARGAZERS,direction:DESC}){
    totalCount nodes{%s languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}}}}
  contributionsCollection{contributionCalendar{totalContributions
    weeks{contributionDays{date contributionCount contributionLevel}}}}}}""" % (REPO_FIELDS, REPO_FIELDS)


def http(url, token=None, payload=None, accept="application/json"):
    headers = {"User-Agent": "profile-artwork", "Accept": accept}
    if token:
        headers["Authorization"] = f"bearer {token}"
    data = json.dumps(payload).encode() if payload else None
    with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=30) as r:
        return r.read().decode()


def pick_work(repos, user):
    repos = [r for r in repos if r["name"].lower() != user.lower()]
    return repos[: CONFIG["work_limit"]]


def fetch_graphql(user, token):
    res = json.loads(http("https://api.github.com/graphql", token,
                          {"query": QUERY, "variables": {"login": user}}))
    if res.get("errors"):
        raise RuntimeError(res["errors"][0].get("message"))
    u = res["data"]["user"]

    def repo(n):
        return {"name": n["name"], "description": n["description"], "url": n["url"],
                "stars": n["stargazerCount"],
                "language": (n["primaryLanguage"] or {}).get("name")}

    langs = {}
    for r in u["repositories"]["nodes"]:
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    pinned = [repo(n) for n in u["pinnedItems"]["nodes"] if n]
    cal = u["contributionsCollection"]["contributionCalendar"]
    return {
        "contributions": cal["totalContributions"],
        "days": [(d["date"], d["contributionCount"], LEVELS[d["contributionLevel"]])
                 for w in cal["weeks"] for d in w["contributionDays"]],
        "languages": langs,
        "repos": u["repositories"]["totalCount"],
        "followers": u["followers"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in u["repositories"]["nodes"]),
        "work": pick_work(pinned or [repo(n) for n in u["repositories"]["nodes"]], user),
    }


def fetch_public(user, token=None):
    """Fallback: the public contribution calendar plus the REST API."""
    page = http(f"https://github.com/users/{user}/contributions", accept="text/html")
    cells = re.findall(r'data-date="(\d{4}-\d\d-\d\d)" id="([\w-]+)" data-level="(\d)"', page)
    tips = dict(re.findall(r'for="([\w-]+)"[^>]*>([^<]*)</tool-tip>', page))
    days = []
    for date, cid, level in cells:
        m = re.match(r"(\d+) contribution", tips.get(cid, ""))
        days.append((date, int(m.group(1)) if m else 0, int(level)))
    days.sort()
    data = {"days": days, "contributions": sum(d[1] for d in days)}
    try:
        profile = json.loads(http(f"https://api.github.com/users/{user}", token))
        repos = json.loads(http(f"https://api.github.com/users/{user}/repos?per_page=100&type=owner", token))
        own = sorted((r for r in repos if not r["fork"]), key=lambda r: -r["stargazers_count"])
        langs = {}
        for r in own:
            if r["language"]:
                langs[r["language"]] = langs.get(r["language"], 0) + max(r["size"], 1)
        data.update(
            repos=len(own), followers=profile["followers"], languages=langs,
            stars=sum(r["stargazers_count"] for r in own),
            work=pick_work([{"name": r["name"], "description": r["description"], "url": r["html_url"],
                             "stars": r["stargazers_count"], "language": r["language"]} for r in own], user))
    except Exception as exc:  # unauthenticated rate limits are common
        print(f"  REST API unavailable ({exc}); repository numbers left blank")
    return data


def fetch_activity(user):
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        try:
            return fetch_graphql(user, token)
        except Exception as exc:
            print(f"  GraphQL failed ({exc}); falling back to public data")
    try:
        return fetch_public(user, token)
    except Exception as exc:
        print(f"  could not reach GitHub ({exc})")
        return {}


def build_activity(F, t, data, today):
    c = Canvas()
    body = section_head(c, F, t, "Activity")

    # metrics
    def fmt(v):
        return f"{v:,}" if isinstance(v, int) else "\u2013"
    metrics = [("Contributions this year", data.get("contributions")),
               ("Public repositories", data.get("repos")),
               ("Stars earned", data.get("stars")),
               ("Followers", data.get("followers"))]
    colw = (W - COL) / 4
    num_base = 46 - 0.729 * 17 + 0.729 * 60
    for j, (label, value) in enumerate(metrics):
        x = COL + j * colw
        body.append(c.text(F["display"], fmt(value), x, num_base, 60, t["ink"], -0.03, optical=True))
        body.append(c.text(F["text"], label, x, num_base + 36, 16, t["muted"]))

    # contribution calendar
    days = data.get("days", [])[-371:]
    y_cal = num_base + 112
    span = W - COL
    weeks = []
    for date, count, level in days:
        d = dt.date.fromisoformat(date)
        if not weeks or d.isoweekday() % 7 == 0:
            weeks.append([])
        weeks[-1].append((d, count, level))
    pitch = span / max(len(weeks), 53)
    cell = pitch * 0.8
    ramp = [t["cell"]] + [mix(t["cell"], t["accent"], a) for a in (0.32, 0.55, 0.78, 1.0)]
    cells, months, last_month = [], [], None
    for wi, week in enumerate(weeks):
        x = COL + wi * pitch
        for d, count, level in week:
            y = y_cal + 26 + (d.isoweekday() % 7) * pitch
            cells.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" '
                         f'rx="2.5" fill="{ramp[level]}"/>')
        first = week[0][0]
        if first.month != last_month and first.day <= 7 and wi < len(weeks) - 2:
            months.append(c.text(F["text"], first.strftime("%b"), x, y_cal + 12, 14, t["muted"]))
            last_month = first.month
    body += months + cells
    y_leg = y_cal + 26 + 7 * pitch + 28
    lx = W - 5 * (cell + 4) - c.measure(F["text"], "More", 14) - 10
    body.append(c.text(F["text"], "Less", lx - 10, y_leg, 14, t["muted"], anchor="end"))
    for i, col in enumerate(ramp):
        body.append(f'<rect x="{lx + i * (cell + 4):.1f}" y="{y_leg - cell + 2:.1f}" width="{cell:.1f}" '
                    f'height="{cell:.1f}" rx="2.5" fill="{col}"/>')
    body.append(c.text(F["text"], "More", W, y_leg, 14, t["muted"], anchor="end"))
    body.append(c.text(F["text"], f"Updated {today.day} {today:%B %Y}", COL, y_leg, 14, t["muted"]))

    # languages
    langs = sorted(data.get("languages", {}).items(), key=lambda kv: -kv[1])
    y = y_leg + 78
    if langs:
        total = sum(v for _, v in langs)
        top = langs[:5]
        rest = total - sum(v for _, v in top)
        if rest / total > 0.01:
            top.append(("Other", rest))
        total = sum(v for _, v in top)
        shades = [t["accent"]] + [mix(t["page"], t["accent"], a) for a in (0.66, 0.44, 0.28, 0.16, 0.08)]
        body.append(c.text(F["text"], "Most used languages", COL, y - 18, 14, t["muted"]))
        x = COL
        gap = 4
        usable = span - gap * (len(top) - 1)
        for i, (name, v) in enumerate(top):
            w = usable * v / total
            body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 2):.1f}" height="10" rx="2" '
                        f'fill="{shades[i]}"/>')
            x += w + gap
        lx, ly = COL, y + 48
        for i, (name, v) in enumerate(top):
            label = f"{name} {100 * v / total:.0f}%"
            wlab = c.measure(F["text"], label, 17) + 20 + 32
            if lx + wlab > W:
                lx, ly = COL, ly + 32
            body.append(f'<rect x="{lx:.1f}" y="{ly - 11:.1f}" width="11" height="11" rx="2" fill="{shades[i]}"/>')
            body.append(c.text(F["text"], name, lx + 20, ly, 17, t["ink"]))
            body.append(c.text(F["text"], f"{100 * v / total:.0f}%",
                               lx + 26 + c.measure(F["text"], name, 17), ly, 17, t["muted"]))
            lx += wlab
        y = ly + 24
    total = data.get("contributions")
    label = f"Activity. {fmt(total)} contributions in the last year."
    return c.render(int(y), "".join(body), label)


# ════════════════════════════════════════════════════════════════════════════
#  README
# ════════════════════════════════════════════════════════════════════════════
def write_readme(pieces):
    """pieces: list of (asset stem, alt text, link or None, gap after: 'section' | 'row' | None)."""
    user = CONFIG["username"]
    branch = os.environ.get("GITHUB_REF_NAME") or "HEAD"
    base = f"https://raw.githubusercontent.com/{user}/{user}/{branch}/assets"
    out = ["<!--",
           "  This README is generated by build.py. Edit CONFIG there, not this file:",
           "  the GitHub Action rebuilds the artwork and this README after every change",
           "  to build.py and once a day for the live Activity numbers.",
           "-->", ""]
    for stem, alt, link, gap in pieces:
        dark = (OUT / f"{stem}-dark.svg").read_bytes()
        light = (OUT / f"{stem}-light.svg").read_bytes()
        v = hashlib.sha1(dark + light).hexdigest()[:8]
        pic = (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{base}/{stem}-dark.svg?v={v}" />'
               f'<img src="{base}/{stem}-light.svg?v={v}" width="100%" alt="{html.escape(alt)}" /></picture>')
        if link:
            pic = f'<a href="{html.escape(link)}">{pic}</a>'
        out.append(pic)
        if gap == "section":
            out += ["", "<br /><br />", ""]
        elif gap == "end":
            out.append("")
    (ROOT / "README.md").write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def main():
    F = fonts()
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    today = dt.date.today()
    print("  fetching activity")
    data = fetch_activity(CONFIG["username"])
    work = data.get("work", [])
    links = CONFIG["links"]

    files = {}
    for name, t in THEMES.items():
        files[f"hero-{name}"] = build_hero(F, t)
        files[f"about-{name}"] = build_about(F, t)
        files[f"stack-{name}"] = build_stack(F, t)
        for i, repo in enumerate(work):
            files[f"work-{i + 1}-{name}"] = build_work_row(F, t, repo, head=i == 0, last=i == len(work) - 1)
        files[f"activity-{name}"] = build_activity(F, t, data, today)
        files[f"contact-{name}"] = build_contact(F, t)
        for i, (label, value, _) in enumerate(links):
            files[f"link-{label.lower()}-{name}"] = build_link_row(F, t, label, value, last=i == len(links) - 1)
        files[f"colophon-{name}"] = build_colophon(F, t, today)
    for stem, svg in files.items():
        (OUT / f"{stem}.svg").write_text(svg, encoding="utf-8")
        print(f"  {stem + '.svg':26s} {len(svg.encode()) / 1024:6.1f} KB")

    pieces = [("hero", f'{CONFIG["name"]}, {CONFIG["role"]}. {CONFIG["tagline"]}', None, "section"),
              ("about", "About. " + CONFIG["about"], None, "section"),
              ("stack", "Stack. " + ". ".join(f"{g}: {', '.join(i)}" for g, i in CONFIG["stack"]), None, "section")]
    for i, repo in enumerate(work):
        pieces.append((f"work-{i + 1}", f'{repo["name"]}: {repo.get("description") or ""}', repo["url"],
                       "section" if i == len(work) - 1 else None))
    pieces.append(("activity", f'Activity: {data.get("contributions", 0)} contributions in the last year', None, "section"))
    pieces.append(("contact", CONFIG["contact_line"], None, "end"))
    for i, (label, value, url) in enumerate(links):
        pieces.append((f"link-{label.lower()}", f"{label}: {value}", url,
                       "section" if i == len(links) - 1 else None))
    pieces.append(("colophon", f'{CONFIG["name"]}, {today.year}', None, None))
    write_readme(pieces)
    print("  README.md")


if __name__ == "__main__":
    main()
