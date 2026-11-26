#!/usr/bin/env python3
"""
Artwork generator for the FilipTw GitHub profile.

    pip install -r requirements.txt
    python build.py

Writes light and dark SVGs into assets/. Text is converted to outlines because
GitHub does not let SVG images load fonts. The GitHub Action in
.github/workflows/profile.yml runs this daily, so the Activity panel stays live
and any change to CONFIG is rebuilt automatically after you commit it.

Typefaces: Mona Sans and Monaspace Neon by GitHub (SIL Open Font License),
downloaded from npm into .fonts/ and checked against the hashes pinned in fontstore.py.
"""

import datetime as dt
import hashlib
import html
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum, auto
from functools import partial
from pathlib import Path
from typing import TypedDict

from activity import Activity, Day, Repo, fetch_activity, http
from canvas import COL, LABEL, LABEL_BASELINE, NOTE, THEMES, Canvas, Fonts, Theme, Type, W, fonts
from hero import build_hero


# ════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════════════════════════════════
class Config(TypedDict):
    username: str
    name: str
    role: str
    tagline: str
    hero_caption: str
    about: str
    facts: list[tuple[str, str]]
    stack: list[tuple[str, list[str]]]
    contact_line: str
    links: list[tuple[str, str, str]]  # (label, text shown, link)
    work_limit: int


CONFIG: Config = {
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
    "links": [
        ("Email", "FilipTw@gmail.com", "mailto:filip.twardawa@gmail.com"),
        ("LinkedIn", "linkedin.com/in/FilipTw", "https://www.linkedin.com/"),
        ("GitHub", "github.com/FilipTw/repositories", "https://github.com/FilipTw?tab=repositories"),
    ],
    # Selected work: the pinned repositories, else the most starred ones.
    "work_limit": 4,
}


ROOT = Path(__file__).resolve().parent
ASSETS = "assets"  # where the SVGs live, relative to the repo root


# ════════════════════════════════════════════════════════════════════════════
#  Editorial Sections, set on the Grid
# ════════════════════════════════════════════════════════════════════════════
def build_about(F: Fonts, t: Theme, alt: str) -> str:
    c = Canvas(F, t)
    body = c.head("About")
    lead, leading = Type("text", 38, "ink", -0.012), 50
    fact, fact_leading = Type("text", 21, "ink"), 29
    facts_gap, label_to_fact, bottom = 76, 34, 20
    lines = c.wrap_balanced(CONFIG["about"], lead, W - COL)
    y = c.first_baseline(lead)
    for i, line in enumerate(lines):
        body.append(c.text(line, COL, y + i * leading, lead, optical=True))
    y += (len(lines) - 1) * leading + facts_gap
    facts = CONFIG["facts"]
    measure = (W - COL) / len(facts) - 40
    max_lines = 2  # the height leaves room for this many lines per fact; more would be cut off
    for (label, value), x in zip(facts, c.columns(len(facts)), strict=True):
        body.append(c.text(label, x, y, LABEL))
        wrapped = c.wrap(value, fact, measure)
        if len(wrapped) > max_lines:
            raise ValueError(f"the {label!r} fact wraps to {len(wrapped)} lines; shorten it to {max_lines}")
        for k, line in enumerate(wrapped):
            body.append(c.text(line, x, y + label_to_fact + k * fact_leading, fact))
    return c.render(int(y + label_to_fact + fact_leading * max_lines + bottom), "".join(body), alt)


def build_stack(F: Fonts, t: Theme, alt: str) -> str:
    c = Canvas(F, t)
    body = c.head("Stack")
    groups = CONFIG["stack"]
    cols = 3
    tool, leading = Type("text", 24, "ink", -0.01), 34
    label_to_tool, row_pad, row_gap = 40, 30, 46
    y = LABEL_BASELINE
    for start in range(0, len(groups), cols):
        row = groups[start : start + cols]
        for (label, items), x in zip(row, c.columns(cols), strict=False):
            body.append(c.text(label, x, y, LABEL))
            for k, item in enumerate(items):
                body.append(c.text(item, x, y + label_to_tool + k * leading, tool))
        tallest = max(len(items) for _, items in row)
        y += row_pad + tallest * leading + row_gap
    return c.render(int(y - row_pad), "".join(body), alt)


def build_contact(F: Fonts, t: Theme, alt: str) -> str:
    c = Canvas(F, t)
    body = c.head("Contact")
    display, leading, bottom = Type("display", 58, "ink", -0.03), 70, 56
    lines = c.wrap_balanced(CONFIG["contact_line"], display, W - COL)
    y = c.first_baseline(display)
    for i, line in enumerate(lines):
        body.append(c.text(line, COL, y + i * leading, display, optical=True))
    return c.render(int(y + (len(lines) - 1) * leading + bottom), "".join(body), alt)


def build_link_row(F: Fonts, t: Theme, alt: str, label: str, value: str, last: bool = False) -> str:
    c = Canvas(F, t)
    H = 78
    label_y, value_x, value_y = 47, COL + 300, 48
    body = [
        c.rule(span="content"),
        c.text(label, COL, label_y, LABEL),
        c.text(value, value_x, value_y, Type("text", 24, "accent", -0.01)),
    ]
    if last:
        body.append(c.rule(H - 1, span="content"))
    return c.render(H, "".join(body), alt)


def build_work_row(F: Fonts, t: Theme, alt: str, repo: Repo, head: bool = False, last: bool = False) -> str:
    c = Canvas(F, t)
    H = 112
    body = c.head("Selected work") if head else [c.rule(span="content")]
    mono, description = Type("mono", 15, "muted"), Type("text", 18, "muted")
    name_y, description_y, description_width = 56, 90, 620
    language_y, stars_y = 52, 88
    body.append(c.text(repo["name"], COL, name_y, Type("display", 34, "ink", -0.02), optical=True))
    desc = c.fit(repo["description"] or "No description yet", description, description_width)
    body.append(c.text(desc, COL, description_y, description))
    if language := repo["language"]:
        body.append(c.text(language, W, language_y, mono, anchor="end"))
    stars = repo["stars"]
    body.append(c.text(f"{stars} star{'' if stars == 1 else 's'}", W, stars_y, mono, anchor="end"))
    if last:
        body.append(c.rule(H - 1, span="content"))
    return c.render(H, "".join(body), alt)


def build_colophon(F: Fonts, t: Theme, alt: str, today: dt.date) -> str:
    c = Canvas(F, t)
    credits = "Set in Mona Sans and Monaspace Neon. Artwork generated with Python."
    body = [
        c.rule(),
        c.text(f"{CONFIG['name']}, {today.year}", 0, LABEL_BASELINE, NOTE),
        c.text(credits, W, LABEL_BASELINE, NOTE, anchor="end"),
    ]
    return c.render(70, "".join(body), alt)


# ════════════════════════════════════════════════════════════════════════════
#  Activity: the live GitHub numbers, drawn
# ════════════════════════════════════════════════════════════════════════════
def fmt_count(v: int | None) -> str:
    """A metric as the profile shows it: 1,234, or a dash when GitHub did not report it."""
    return f"{v:,}" if isinstance(v, int) else "–"


LEGEND = Type("text", 14, "muted")  # the calendar's legend row and the languages' Label


def contribution_calendar(
    c: Canvas, days: list[Day], y_cal: float, today: dt.date
) -> tuple[list[str], float]:
    """One column of cells per week, full width like the hero so the cells stay legible, the months above
    and the legend row below. Returns the drawing and the legend's baseline."""
    weeks: list[list[tuple[dt.date, int, int]]] = []
    for date, count, level in days[-371:]:
        d = dt.date.fromisoformat(date)
        if not weeks or d.isoweekday() % 7 == 0:
            weeks.append([])
        weeks[-1].append((d, count, level))
    pitch = W / max(len(weeks), 53)
    cell = pitch * 0.82
    ramp = c.t.calendar_ramp
    cols, months, last_month = [], [], None
    for wi, week in enumerate(weeks):
        x = wi * pitch
        rects = "".join(
            f'<rect x="{x:.1f}" y="{y_cal + 30 + (d.isoweekday() % 7) * pitch:.1f}" '
            f'width="{cell:.1f}" height="{cell:.1f}" rx="3.5" fill="{ramp[level]}"/>'
            for d, count, level in week
        )
        cols.append(f'<g class="wk" style="animation-delay:{0.15 + wi * 0.02:.2f}s">{rects}</g>')
        first = week[0][0]
        if first.month != last_month and first.day <= 7 and wi < len(weeks) - 2:
            months.append(c.text(first.strftime("%b"), x, y_cal + 14, Type("text", 15, "muted")))
            last_month = first.month
    body = months + cols
    c.css.append(
        ".wk{animation:wk 1s cubic-bezier(.19,1,.22,1) both}"
        "@keyframes wk{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}"
        "@media (prefers-reduced-motion:reduce){.wk{animation:none!important}}"
    )
    y_leg = y_cal + 30 + 7 * pitch + 30
    key = 13
    lx = W - 5 * (key + 4) - c.measure("More", LEGEND) - 10
    body.append(c.text("Less", lx - 10, y_leg, LEGEND, anchor="end"))
    for i, col in enumerate(ramp):
        body.append(
            f'<rect x="{lx + i * (key + 4):.1f}" y="{y_leg - key + 1:.1f}" width="{key}" '
            f'height="{key}" rx="2.5" fill="{col}"/>'
        )
    body.append(c.text("More", W, y_leg, LEGEND, anchor="end"))
    body.append(c.text(f"Updated {today.day} {today:%B %Y}", 0, y_leg, LEGEND))
    return body, y_leg


def language_bars(c: Canvas, languages: dict[str, int], y_leg: float) -> tuple[list[str], float]:
    """The five most used languages and the rest as Other, as one bar and a key. Returns the drawing and
    the y where the Section ends."""
    langs = sorted(languages.items(), key=lambda kv: -kv[1])
    if not langs:
        return [], y_leg + 24
    body = []
    y = y_leg + 78
    total = sum(v for _, v in langs)
    top = langs[:5]
    rest = total - sum(v for _, v in top)
    if rest / total > 0.01:
        top.append(("Other", rest))
    total = sum(v for _, v in top)
    shades = c.t.language_shades
    body.append(c.text("Most used languages", COL, y - 18, LEGEND))
    x: float = COL
    gap = 4
    usable = W - COL - gap * (len(top) - 1)
    for i, (_, v) in enumerate(top):
        w = usable * v / total
        body.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 2):.1f}" height="10" rx="2" fill="{shades[i]}"/>'
        )
        x += w + gap
    lx: float = COL
    ly = y + 48
    language, share = Type("text", 17, "ink"), Type("text", 17, "muted")
    for i, (name, v) in enumerate(top):
        percent = f"{100 * v / total:.0f}%"
        label = f"{name} {percent}"
        wlab = c.measure(label, language) + 20 + 32
        if lx + wlab > W:
            lx, ly = COL, ly + 32
        body.append(
            f'<rect x="{lx:.1f}" y="{ly - 11:.1f}" width="11" height="11" rx="2" fill="{shades[i]}"/>'
        )
        body.append(c.text(name, lx + 20, ly, language))
        body.append(c.text(percent, lx + 26 + c.measure(name, language), ly, share))
        lx += wlab
    return body, ly + 24


def build_activity(F: Fonts, t: Theme, alt: str, activity: Activity, today: dt.date) -> str:
    c = Canvas(F, t)
    body = c.head("Activity")
    metrics = [
        ("Contributions this year", activity.contributions),
        ("Public repositories", activity.repos),
        ("Stars earned", activity.stars),
        ("Followers", activity.followers),
    ]
    figure = Type("display", 60, "ink", -0.03)
    num_base = c.first_baseline(figure)
    for (label, value), x in zip(metrics, c.columns(len(metrics)), strict=True):
        body.append(c.text(fmt_count(value), x, num_base, figure, optical=True))
        body.append(c.text(label, x, num_base + 36, NOTE))
    calendar, y_leg = contribution_calendar(c, activity.days or [], num_base + 112, today)
    languages, y = language_bars(c, activity.languages or {}, y_leg)
    return c.render(int(y), "".join(body + calendar + languages), alt)


# ════════════════════════════════════════════════════════════════════════════
#  Profile: the ordered Sections, rendered into every file the README needs
# ════════════════════════════════════════════════════════════════════════════
class Gap(Enum):
    """Space the README leaves after a Section."""

    SECTION = auto()  # a visible break before the next Section
    END = auto()  # one blank line, so the next picture starts a new paragraph
    NONE = auto()  # the next picture follows directly (rows of one group)


@dataclass(frozen=True)
class Section:
    """One strip of the profile: a light and a dark SVG, and one picture in the README."""

    stem: str
    alt: str
    draw: Callable[[Fonts, Theme, str], str]  # (fonts, Theme, alt) -> SVG
    link: str | None = None
    gap: Gap = Gap.NONE


def row_group(rows: list[Section]) -> list[Section]:
    """Rows of one group follow each other directly; the last one ends the group with a Section break."""
    return rows[:-1] + [replace(rows[-1], gap=Gap.SECTION)] if rows else rows


def work_alt(repo: Repo) -> str:
    return f"{repo['name']}. {repo['description']}" if repo["description"] else repo["name"]


def sections(activity: Activity, today: dt.date) -> list[Section]:
    """Every Section of the profile, in README order."""
    work = activity.work or []
    links = CONFIG["links"]
    return [
        Section(
            "hero",
            f"{CONFIG['name']}, {CONFIG['role']}. {CONFIG['tagline']}",
            partial(
                build_hero,
                name=CONFIG["name"],
                role=CONFIG["role"],
                tagline=CONFIG["tagline"],
                caption=CONFIG["hero_caption"],
            ),
            gap=Gap.SECTION,
        ),
        Section("about", "About. " + CONFIG["about"], build_about, gap=Gap.SECTION),
        Section(
            "stack",
            "Stack. " + ". ".join(f"{g}: {', '.join(i)}" for g, i in CONFIG["stack"]),
            build_stack,
            gap=Gap.SECTION,
        ),
        *row_group(
            [
                Section(
                    f"work-{i + 1}",
                    work_alt(repo),
                    partial(build_work_row, repo=repo, head=i == 0, last=i == len(work) - 1),
                    link=repo["url"],
                )
                for i, repo in enumerate(work)
            ]
        ),
        Section(
            "activity",
            f"Activity. {fmt_count(activity.contributions)} contributions in the last year.",
            partial(build_activity, activity=activity, today=today),
            gap=Gap.SECTION,
        ),
        Section("contact", CONFIG["contact_line"], build_contact, gap=Gap.END),
        *row_group(
            [
                Section(
                    f"link-{label.lower()}",
                    f"{label}: {value}",
                    partial(build_link_row, label=label, value=value, last=i == len(links) - 1),
                    link=url,
                )
                for i, (label, value, url) in enumerate(links)
            ]
        ),
        Section("colophon", f"{CONFIG['name']}, {today.year}", partial(build_colophon, today=today)),
    ]


def render_readme(svgs: list[tuple[Section, dict[str, str]]], branch: str) -> str:
    """svgs: [(Section, {Theme name: SVG})]. Each picture URL carries a hash of its SVGs to bust caches."""
    user = CONFIG["username"]
    base = f"https://raw.githubusercontent.com/{user}/{user}/{branch}/assets"
    out = [
        "<!--",
        "  This README is generated by build.py. Edit CONFIG there, not this file:",
        "  the GitHub Action rebuilds the artwork and this README after every change",
        "  to the Python code and once a day for the live Activity numbers.",
        "-->",
        "",
    ]
    for s, by_theme in svgs:
        v = hashlib.sha1((by_theme["dark"] + by_theme["light"]).encode()).hexdigest()[:8]
        pic = (
            f'<picture><source media="(prefers-color-scheme: dark)" '
            f'srcset="{base}/{s.stem}-dark.svg?v={v}" />'
            f'<img src="{base}/{s.stem}-light.svg?v={v}" width="100%" alt="{html.escape(s.alt)}" /></picture>'
        )
        if s.link:
            pic = f'<a href="{html.escape(s.link)}">{pic}</a>'
        out.append(pic)
        if s.gap is Gap.SECTION:
            out += ["", "<br /><br />", ""]
        elif s.gap is Gap.END:
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def build_profile(activity: Activity, today: dt.date, F: Fonts, branch: str) -> dict[str, str]:
    """Every generated file, as {path relative to the repo root: text}. Pure: nothing is read or written."""
    svgs = [(s, {name: s.draw(F, t, s.alt) for name, t in THEMES.items()}) for s in sections(activity, today)]
    files = {f"{ASSETS}/{s.stem}-{name}.svg": svg for s, by_theme in svgs for name, svg in by_theme.items()}
    files["README.md"] = render_readme(svgs, branch)
    return files


def write_profile(files: dict[str, str], root: Path) -> None:
    """Write the built files under root, then remove SVGs of Sections that no longer exist."""
    assets = root / ASSETS
    assets.mkdir(exist_ok=True)
    for path, text in files.items():
        (root / path).write_text(text, encoding="utf-8")
        print(f"  {path:33s} {len(text.encode()) / 1024:6.1f} KB")
    for old in assets.glob("*.svg"):
        if f"{ASSETS}/{old.name}" not in files:
            old.unlink()
            print(f"  removed {ASSETS}/{old.name}")


def main() -> None:
    F = fonts()
    print("  fetching activity")
    activity = fetch_activity(
        CONFIG["username"], os.environ.get("GITHUB_TOKEN"), http, work_limit=CONFIG["work_limit"]
    )
    if os.environ.get("CI") and not activity.complete:
        raise SystemExit("  incomplete data from GitHub; keeping the previous artwork")
    branch = os.environ.get("GITHUB_REF_NAME") or "HEAD"
    write_profile(build_profile(activity, dt.date.today(), F, branch), ROOT)


if __name__ == "__main__":
    main()
