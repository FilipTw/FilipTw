"""Hero: gradient descent on a toy loss surface, with the name set large across it."""

from functools import cache
from typing import cast

import contourpy
import numpy as np
import numpy.typing as npt

from canvas import LABEL, Canvas, Fonts, Theme, Type, W

Points = npt.NDArray[np.float64]  # an (n, 2) array of x, y
HERO_H = 760
TARGET = (845.0, 262.0)
DESCENT_START, DESCENT_TIME = 1.25, 3.6  # seconds: when the marker sets off, how long it takes
NAME_BASELINE = 636


def loss(x: npt.ArrayLike, y: npt.ArrayLike) -> Points:
    x, y = np.asarray(x, float) / 1000, np.asarray(y, float) / 1000
    gx, gy = TARGET[0] / 1000, TARGET[1] / 1000
    u, v = (x - gx) / 0.20, (y - gy) / 0.11
    f = -1.00 * np.exp(-(u * u + v * v - 0.9 * u * v))
    f -= 0.55 * np.exp(-(((x - 0.30) / 0.17) ** 2 + ((y - 0.52) / 0.14) ** 2))
    f -= 0.30 * np.exp(-(((x - 0.62) / 0.10) ** 2 + ((y - 0.62) / 0.10) ** 2))
    f += 0.55 * ((x - 0.70) ** 2 + 1.2 * (y - 0.32) ** 2)
    f += 0.035 * np.sin(11 * x + 1.3) * np.cos(9 * y + 0.4)
    return f


@cache
def descent(
    start: tuple[float, float] = (110.0, 128.0),
    lr: float = 2500.0,
    beta: float = 0.88,
    steps: int = 220,
    h: float = 0.5,
) -> Points:
    p, vel, pts = np.array(start), np.zeros(2), [np.array(start)]
    for _ in range(steps):
        g = np.array(
            [
                (loss(p[0] + h, p[1]) - loss(p[0] - h, p[1])) / (2 * h),
                (loss(p[0], p[1] + h) - loss(p[0], p[1] - h)) / (2 * h),
            ]
        )
        vel = beta * vel - lr * g
        p = p + vel
        pts.append(p.copy())
    path = np.array(pts)
    moving = np.hypot(*np.diff(path, axis=0).T) > 0.35
    last = len(moving) - int(np.argmax(moving[::-1]))
    return path[: last + 1]


def smooth(pts: Points, times: list[float], step: float = 7.0) -> tuple[Points, list[float]]:
    """Catmull-Rom resampling so the trail and the marker share one smooth curve."""
    out_p, out_t = [pts[0]], [times[0]]
    n = len(pts)
    for i in range(n - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, n - 1)]
        k = max(1, int(np.ceil(np.hypot(*(p2 - p1)) / step)))
        for j in range(1, k + 1):
            u = j / k
            q = 0.5 * (
                (2 * p1)
                + (-p0 + p2) * u
                + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u**2
                + (-p0 + 3 * p1 - 3 * p2 + p3) * u**3
            )
            out_p.append(q)
            out_t.append(times[i] + (times[i + 1] - times[i]) * u)
    return np.array(out_p), out_t


def simplify(pts: Points, eps: float) -> Points:
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ab = b - a
    n = np.hypot(*ab)
    d = (
        np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / n
        if n > 1e-9
        else np.hypot(*(pts - a).T)
    )
    i = int(np.argmax(d))
    if d[i] > eps:
        return np.vstack([simplify(pts[: i + 1], eps)[:-1], simplify(pts[i:], eps)])
    return np.vstack([a, b])


def inside(poly: Points, pt: tuple[float, float]) -> bool:
    x, y = pt
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, np.roll(poly, -1, axis=0), strict=True):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


@cache  # both Themes share the result, as with descent: read it, never mutate it
def contour_lines(
    levels: int = 34, res: float = 3.0, pad: int = 40
) -> tuple[list[tuple[int, Points, bool]], float]:
    xs, ys = np.arange(-pad, W + pad, res), np.arange(-pad, HERO_H + pad, res)
    X, Y = np.meshgrid(xs, ys)
    Z = loss(X, Y)
    gen = contourpy.contour_generator(X, Y, Z, line_type=contourpy.LineType.Separate)
    out = []
    for k, level in enumerate(np.linspace(Z.min() + 0.02, np.percentile(Z, 92), levels)):
        for line in cast(list[Points], gen.lines(level)):  # LineType.Separate: one array per line
            if len(line) >= 6:
                line = simplify(line, 0.35)
                closed = np.allclose(line[0], line[-1])
                out.append((k, line, closed and inside(line, TARGET)))
    return out, float(Z.min())


def poly_d(pts: Points) -> str:
    return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts)


def hero_contours(c: Canvas) -> str:
    """Contour lines of the loss surface, drawn in; the rings round the minimum lean to the accent."""
    lines, _ = contour_lines()
    k_inner = max(k for k, _, hit in lines if hit) + 1
    paths = []
    for k, line, hit in lines:
        depth = 1 - k / k_inner
        tint = min(max((depth - 0.42) / 0.58, 0), 1) ** 1.3 if hit else 0
        stroke, width = c.t.contour_stroke(tint), 1.1 + 0.4 * tint
        paths.append(
            f'<path class="ct" pathLength="1" style="animation-delay:{0.05 + k * 0.032:.3f}s" '
            f'd="{poly_d(line)}" stroke="{stroke}" stroke-width="{width:.2f}"/>'
        )
    c.extra.append(
        f'<radialGradient id="rad" gradientUnits="userSpaceOnUse" cx="790" cy="300" r="820">'
        f'<stop offset=".45" stop-color="#fff"/><stop offset="1" stop-color="#000"/></radialGradient>'
        f'<linearGradient id="vfade" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="{HERO_H}">'
        f'<stop offset="0" stop-opacity=".9"/><stop offset=".13" stop-opacity="0"/>'
        f'<stop offset=".5" stop-opacity="0"/><stop offset=".9" stop-opacity=".92"/></linearGradient>'
        f'<mask id="fade" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{HERO_H}">'
        f'<rect width="{W}" height="{HERO_H}" fill="url(#rad)"/>'
        f'<rect width="{W}" height="{HERO_H}" fill="url(#vfade)"/></mask>'
    )
    c.css.append(
        ".ct{stroke-dasharray:1 1;animation:draw 2.2s cubic-bezier(.65,0,.35,1) both}"
        "@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
    )
    return f'<g fill="none" mask="url(#fade)">{"".join(paths)}</g>'


def hero_descent(c: Canvas, pts: Points, times: list[float]) -> list[str]:
    """The start ring, the trail with the marker riding along it, and their notes."""
    t, t0, dur = c.t, DESCENT_START, DESCENT_TIME
    curve, ctimes = smooth(pts, times)
    seg = np.hypot(*np.diff(curve, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)]) / seg.sum()
    # max(): the last offset is 1 - 1.0000000000000002 on some platforms, which would print as -0.0000
    trail_kf = "".join(
        f"{(ti - t0) / dur * 100:.2f}%{{stroke-dashoffset:{max(1 - ci, 0.0):.4f}}}"
        for ti, ci in zip(ctimes, cum, strict=True)
    )
    move_kf = "".join(
        f"{(ti - t0) / dur * 100:.2f}%{{transform:translate({x:.1f}px,{y:.1f}px)}}"
        for ti, (x, y) in zip(ctimes, curve, strict=True)
    )
    c.css.append(
        f".trail{{stroke-dasharray:1 1;animation:trail {dur}s linear {t0}s both}}"
        f"@keyframes trail{{{trail_kf}}}"
        f".dot{{animation:move {dur}s linear {t0}s both}}@keyframes move{{{move_kf}}}"
    )
    c.css.append(
        f".pulse{{transform-box:fill-box;transform-origin:center;"
        f"animation:pulse 2.8s cubic-bezier(.2,.6,.3,1) {t0 + dur:.2f}s infinite both}}"
        "@keyframes pulse{0%{transform:scale(1);opacity:.8}100%{transform:scale(4.2);opacity:0}}"
    )
    sx, sy = pts[0]
    ex, ey = pts[-1]
    note = Type("mono", 14, "muted")
    start_delay = f"animation-delay:{t0 - 0.3}s"
    lx, ly = ex + 150, ey - 112
    return [
        f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="4.5" fill="none" stroke="{t.muted}" '
        f'stroke-width="1.4" class="fd" style="{start_delay}"/>',
        f'<path class="trail" pathLength="1" d="{poly_d(curve)}" fill="none" stroke="{t.accent}" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
        f'<g class="dot" transform="translate({ex:.1f} {ey:.1f})">'
        f'<circle class="pulse" r="7" fill="none" stroke="{t.accent}" stroke-width="1.4"/>'
        f'<circle r="13" fill="{t.accent}" opacity=".16"/>'
        f'<circle r="6" fill="{t.accent}"/></g>',
        f'<g class="fd" style="animation-delay:{t0 + dur:.2f}s">'
        f'<path d="M{ex + 10:.1f} {ey - 10:.1f}L{lx - 40:.1f} {ly:.1f}H{lx - 8:.1f}" fill="none" '
        f'stroke="{t.muted}" stroke-width="1"/>' + c.text("minimum", lx, ly + 5, note) + "</g>",
        c.text("init", sx, sy + 30, note, anchor="middle", attrs=f' class="fd" style="{start_delay}"'),
    ]


def hero_readout(c: Canvas, pts: Points, times: list[float], caption: str) -> str:
    """The top row: the caption, and an epoch and loss readout that counts along with the marker."""
    _, zmin = contour_lines()
    n = len(pts)
    top_row = 38
    fade_in = ' class="fd" style="animation-delay:.2s"'
    caption = c.text(caption, 0, top_row, LABEL, attrs=fade_in)
    reading, reading_value = Type("mono", 16, "muted"), Type("mono", 16, "ink")
    adv = c.measure("0", reading)
    loss_scale = 2.4 / (loss(*pts[0]) - zmin)
    x_loss_val = W - 6 * adv
    x_loss_lab = x_loss_val - adv * 5.2
    x_ep_val = x_loss_lab - adv * 6.5
    x_ep_lab = x_ep_val - adv * 6.2
    readout = [
        c.text("epoch", x_ep_lab, top_row, reading),
        c.text("loss", x_loss_lab, top_row, reading),
    ]
    frames = list(range(0, n, 2))
    if frames[-1] != n - 1:
        frames.append(n - 1)
    for j, i in enumerate(frames):
        value = (loss(*pts[i]) - zmin) * loss_scale + 0.0021
        group = c.text(f"{i:03d}", x_ep_val, top_row, reading_value) + c.text(
            f"{value:.4f}", x_loss_val, top_row, reading_value
        )
        if j == len(frames) - 1:
            style = f"animation:off {times[i]:.3f}s step-end"
            readout.append(f'<g class="fr last" style="{style}">{group}</g>')
        else:
            start = 0 if j == 0 else times[i]
            end = times[frames[j + 1]]
            style = f"animation:on {end - start:.3f}s step-end {start:.3f}s"
            readout.append(f'<g class="fr" style="{style}">{group}</g>')
    c.css.append(
        ".fr{opacity:0}.fr.last{opacity:1}@keyframes on{0%,100%{opacity:1}}@keyframes off{0%,100%{opacity:0}}"
    )
    return caption + f"<g{fade_in}>{''.join(readout)}</g>"


def hero_name(c: Canvas, name: str) -> str:
    """The name across the left, its letters rising into place one by one."""
    track, base = -0.03, NAME_BASELINE
    size = 680 / c.measure(name, Type("display", 1000, "ink", track)) * 1000
    cap = c.F["display"].cap_height * size
    letters = c.glyphs(name, 0, base, Type("display", size, "ink", track), optical=True)
    els = "".join(
        f'<g class="ch" style="animation-delay:{0.35 + i * 0.075:.3f}s">{c.use(*g)}</g>'
        for i, g in enumerate(letters)
    )
    top, bottom = base - cap - 40, base + 0.32 * size
    c.extra.append(
        f'<clipPath id="nm"><rect x="-20" y="{top:.0f}" width="{W + 40}" '
        f'height="{bottom - top:.0f}"/></clipPath>'
    )
    c.css.append(
        ".ch{animation:rise 1.4s cubic-bezier(.19,1,.22,1) both}"
        f"@keyframes rise{{from{{transform:translateY({bottom - top:.0f}px)}}to{{transform:none}}}}"
    )
    return f'<g clip-path="url(#nm)" fill="{c.t.ink}">{els}</g>'


def hero_byline(c: Canvas, role: str, tagline: str) -> str:
    """The role over the tagline, bottom right; the tagline's last line sits on the name's baseline."""
    bx, bw = 812, W - 812
    setting = Type("text", 19, "muted")
    tag = c.wrap(tagline, setting, bw)
    first = NAME_BASELINE - (len(tag) - 1) * 27
    block = [c.text(line, bx, first + i * 27, setting) for i, line in enumerate(tag)]
    block.append(c.text(role, bx, first - 40, Type("medium", 23, "ink")))
    return f'<g class="fd" style="animation-delay:.95s">{"".join(block)}</g>'


def build_hero(F: Fonts, t: Theme, alt: str, *, name: str, role: str, tagline: str, caption: str) -> str:
    c = Canvas(F, t)
    pts = descent()
    n = len(pts)
    times = [DESCENT_START + DESCENT_TIME * i / (n - 1) for i in range(n)]
    body = [
        hero_contours(c),
        *hero_descent(c, pts, times),
        hero_readout(c, pts, times, caption),
        hero_name(c, name),
        hero_byline(c, role, tagline),
    ]
    c.css.append(
        ".fd{animation:fd 1.3s cubic-bezier(.19,1,.22,1) both}"
        "@keyframes fd{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}"
        "@media (prefers-reduced-motion:reduce){.ct,.trail,.dot,.pulse,.ch,.fd,.fr{animation:none!important}}"
    )
    return c.render(HERO_H, "".join(body), alt)
