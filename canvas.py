"""The drawing kit every Section shares: the Themes, the Fonts, and a Canvas that sets type as outlines
on the Grid."""

import html
import io
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Literal

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

import fontstore


# ════════════════════════════════════════════════════════════════════════════
#  Design tokens
# ════════════════════════════════════════════════════════════════════════════
def mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i : i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb, strict=True))


Role = Literal["page", "ink", "muted", "faint", "line", "contour", "accent", "cell"]


@dataclass(frozen=True)
class Theme:
    """Hex colours by role."""

    page: str
    ink: str
    muted: str
    faint: str
    line: str
    contour: str
    accent: str
    cell: str

    def colour(self, role: Role) -> str:
        return str(getattr(self, role))

    @property
    def calendar_ramp(self) -> list[str]:
        """One colour per contribution level, 0 (none) to 4."""
        return [self.cell] + [mix(self.cell, self.accent, a) for a in (0.4, 0.62, 0.82, 1.0)]

    @property
    def language_shades(self) -> list[str]:
        """The language bars, most used first."""
        return [self.accent] + [mix(self.page, self.accent, a) for a in (0.66, 0.44, 0.28, 0.16, 0.08)]

    def contour_stroke(self, tint: float) -> str:
        """A hero contour line; tint 0 to 1 draws it toward the accent near the minimum."""
        return mix(self.contour, self.accent, 0.12 + 0.88 * tint) if tint > 0 else self.contour


THEMES: dict[str, Theme] = {
    "light": Theme(
        page="#FFFFFF",
        ink="#0A0B0D",
        muted="#676C75",
        faint="#A5AAB2",
        line="#E2E4E8",
        contour="#CDD1D8",
        accent="#2B3BFF",
        cell="#E8EBEF",
    ),
    "dark": Theme(
        page="#0D1117",
        ink="#EEF1F5",
        muted="#8C939D",
        faint="#565D67",
        line="#262C35",
        contour="#28303B",
        accent="#7D87FF",
        cell="#1D232C",
    ),
}

W = 1200  # every SVG shares this width, so edges align in the README
COL = 300  # the Grid: the label column ends and the content column starts here
FONT_DIR = Path(__file__).resolve().parent / ".fonts"


# ════════════════════════════════════════════════════════════════════════════
#  Type engine: shape with HarfBuzz, draw outlines with fontTools
# ════════════════════════════════════════════════════════════════════════════
class Font:
    def __init__(self, key: str, data: bytes, location: dict[str, float] | None = None) -> None:
        """data is a font file (woff2 included); location picks an instance of a variable font."""
        self.tt = TTFont(io.BytesIO(data))
        self.tt.flavor = None  # HarfBuzz reads plain sfnt, not woff2
        sfnt = io.BytesIO()
        self.tt.save(sfnt)
        self.key, self.location = key, location or {}
        self.hb = hb.Font(hb.Face(sfnt.getvalue()))
        if self.location:
            self.hb.set_variations(self.location)
        self.upem = self.tt["head"].unitsPerEm
        self.cap_height = self.tt["OS/2"].sCapHeight / self.upem
        self.glyphs = self.tt.getGlyphSet(location=self.location or None)
        self.order = self.tt.getGlyphOrder()

    def shape(self, text: str) -> list[tuple[str, int, int, int]]:
        """(glyph name, x advance, x offset, y offset) per glyph, in font units."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "liga": True})
        return [
            (self.order[i.codepoint], p.x_advance, p.x_offset, p.y_offset)
            for i, p in zip(buf.glyph_infos, buf.glyph_positions, strict=True)
        ]

    def outline(self, glyph: str) -> str:
        pen = SVGPathPen(self.glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
        self.glyphs[glyph].draw(pen)
        return pen.getCommands()

    def lsb(self, text: str) -> float:
        """Left side bearing of the first glyph, for optical left alignment."""
        glyph = self.shape(text)[0][0]
        pen = BoundsPen(self.glyphs)
        self.glyphs[glyph].draw(pen)
        return pen.bounds[0] if pen.bounds else 0


Fonts = dict[str, Font]  # role (display, text, mono, ...) -> Font


@dataclass(frozen=True)
class Type:
    """Size in px; tracking in ems, as in CSS letter-spacing."""

    font: str
    size: float
    colour: Role
    tracking: float = 0.0


Glyph = tuple[str, float, float, float]  # (outline id, x, y, scale)
LABEL = Type("text", 17, "muted")
NOTE = Type("text", 16, "muted")  # a step below a Label: the colophon, the names under the metrics
LABEL_BASELINE = 46  # a Section's Label sits on this baseline, below the opening Rule


class Canvas:
    """One SVG being drawn with the profile's Fonts and one Theme; glyph outlines are shared as <defs>."""

    def __init__(self, F: Fonts, t: Theme) -> None:
        self.F, self.t = F, t
        self.defs: dict[str, str] = {}
        self.extra: list[str] = []
        self.css: list[str] = []

    def gid(self, font: Font, glyph: str) -> str:
        key = f"{font.key}-{glyph}".replace(".", "_")
        if key not in self.defs:
            self.defs[key] = font.outline(glyph)
        return key

    def measure(self, text: str, setting: Type) -> float:
        font, size = self.F[setting.font], setting.size
        run = font.shape(text)
        return sum(r[1] for r in run) * size / font.upem + setting.tracking * size * max(len(run) - 1, 0)

    def glyphs(
        self, text: str, x: float, y: float, setting: Type, *, anchor: str = "start", optical: bool = False
    ) -> list[Glyph]:
        font, size = self.F[setting.font], setting.size
        s = size / font.upem
        if anchor != "start":
            w = self.measure(text, setting)
            x -= w if anchor == "end" else w / 2
        if optical:
            x -= font.lsb(text) * s
        out, pen = [], x
        for glyph, adv, dx, dy in font.shape(text):
            key = self.gid(font, glyph)
            if self.defs[key]:
                out.append((key, pen + dx * s, y - dy * s, s))
            pen += adv * s + setting.tracking * size
        return out

    @staticmethod
    def use(key: str, x: float, y: float, s: float) -> str:
        return f'<use href="#{key}" transform="translate({x:.2f} {y:.2f}) scale({s:.5f} {-s:.5f})"/>'

    def text(
        self,
        text: str,
        x: float,
        y: float,
        setting: Type,
        *,
        anchor: str = "start",
        optical: bool = False,
        attrs: str = "",
    ) -> str:
        run = self.glyphs(text, x, y, setting, anchor=anchor, optical=optical)
        inner = "".join(self.use(*g) for g in run)
        return f'<g fill="{self.t.colour(setting.colour)}"{attrs}>{inner}</g>'

    def wrap(self, text: str, setting: Type, width: float) -> list[str]:
        lines, line = [], ""
        for word in text.split():
            trial = f"{line} {word}".strip()
            if line and self.measure(trial, setting) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        return lines + [line] if line else lines

    def wrap_balanced(self, text: str, setting: Type, width: float) -> list[str]:
        """Wrap, then narrow the measure until the last line is not a lone word."""
        lines, w = self.wrap(text, setting, width), width
        while len(lines) > 1 and len(lines[-1].split()) < 2 and w > width * 0.75:
            w -= 8
            lines = self.wrap(text, setting, w)
        return lines

    def fit(self, text: str, setting: Type, width: float) -> str:
        """The text, cut short with an ellipsis if it is wider than width."""
        if self.measure(text, setting) <= width:
            return text
        while text and self.measure(text + "\u2026", setting) > width:
            text = text[:-1]
        return text.rstrip(" ,.;:") + "\u2026"

    def rule(self, y: int = 0, span: Literal["full", "content"] = "full") -> str:
        x = 0 if span == "full" else COL
        return f'<rect x="{x}" y="{y}" width="{W - x}" height="1" fill="{self.t.line}"/>'

    def head(self, label: str) -> list[str]:
        """How a Section opens: a full-width Rule, then its Label in the label column."""
        return [self.rule(), self.text(label, 0, LABEL_BASELINE, LABEL)]

    @staticmethod
    def columns(n: int) -> list[float]:
        """The x of each of n equal columns across the content column."""
        width = (W - COL) / n
        return [COL + j * width for j in range(n)]

    def first_baseline(self, setting: Type) -> float:
        """The baseline that puts the cap height of a first line level with the Label's."""
        label = self.F[LABEL.font].cap_height * LABEL.size
        return LABEL_BASELINE - label + self.F[setting.font].cap_height * setting.size

    def render(self, height: int, body: str, label: str) -> str:
        defs = "".join(f'<path id="{k}" d="{d}"/>' for k, d in self.defs.items() if d)
        style = f"<style>{''.join(self.css)}</style>" if self.css else ""
        label = html.escape(label)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" '
            f'width="{W}" height="{height}" role="img" aria-label="{label}">'
            f"<title>{label}</title><defs>{defs}{''.join(self.extra)}{style}</defs>"
            f"{body}</svg>"
        )


def fonts() -> Fonts:
    load = partial(fontstore.load, cache_dir=FONT_DIR)
    mona = load("mona-sans-latin-wdth-normal.woff2")
    return {
        "display": Font("d", mona, {"wdth": 125, "wght": 300}),
        "text": Font("t", mona, {"wdth": 100, "wght": 420}),
        "medium": Font("m", mona, {"wdth": 100, "wght": 540}),
        "mono": Font("c", load("monaspace-neon-latin-400-normal.woff2")),
    }
