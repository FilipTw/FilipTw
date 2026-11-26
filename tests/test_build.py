"""The whole profile, built from fixed inputs, must match tests/golden/."""

import datetime as dt
import json
import re
import shutil
import typing
from dataclasses import fields
from pathlib import Path

import pytest

import build
import canvas
from activity import Activity

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
TODAY = dt.date(2026, 6, 15)
BRANCH = "main"


def fixture_activity():
    return Activity(**json.loads((HERE / "fixtures" / "activity.json").read_text()))


@pytest.fixture(scope="module")
def files():
    return build.build_profile(fixture_activity(), TODAY, build.fonts(), BRANCH)


def read_tree(root):
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.name.startswith(".")
    }  # skip .DS_Store


def test_profile_matches_golden(files, request):
    if request.config.getoption("--update-golden"):
        shutil.rmtree(GOLDEN, ignore_errors=True)
        for path, text in files.items():
            (GOLDEN / path).parent.mkdir(parents=True, exist_ok=True)
            (GOLDEN / path).write_text(text, encoding="utf-8")
        pytest.skip("golden files updated")
    golden = read_tree(GOLDEN)
    assert sorted(files) == sorted(golden)
    for path in golden:
        assert files[path] == golden[path], f"{path} differs from tests/golden/{path}"


def test_written_profile_is_exactly_the_built_files(files, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "work-9-light.svg").write_text("<svg/>")  # a Section that no longer exists
    build.write_profile(files, tmp_path)
    assert read_tree(tmp_path) == files


def test_readme_alt_text_matches_each_svg_title(files):
    alts = re.findall(
        r'srcset="[^"]*/assets/([\w-]+)-dark\.svg\?v=\w+" /><img [^>]* alt="([^"]*)"', files["README.md"]
    )
    assert alts, "no pictures found in README.md"
    for stem, alt in alts:
        for theme in build.THEMES:
            title = re.search(r"<title>([^<]*)</title>", files[f"assets/{stem}-{theme}.svg"])
            assert title, f"{stem}-{theme}.svg has no <title>"
            assert alt == title.group(1), f"{stem}: README says {alt!r}, SVG says {title.group(1)!r}"


def test_main_keeps_the_previous_artwork_when_ci_gets_incomplete_activity(monkeypatch, tmp_path):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "fetch_activity", lambda *args, **kwargs: Activity(repos=3))
    monkeypatch.setenv("CI", "true")
    with pytest.raises(SystemExit):
        build.main()
    assert list(tmp_path.iterdir()) == []


def test_main_links_the_readme_to_head_outside_github_actions(monkeypatch, tmp_path):
    activity = fixture_activity()
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "fetch_activity", lambda *args, **kwargs: activity)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    build.main()
    assert f"/{build.CONFIG['username']}/HEAD/assets/hero-light.svg" in (tmp_path / "README.md").read_text()


def test_mona_sans_cap_height_matches_the_grid_it_was_designed_with():
    """The Grid lines up first lines by cap height; another font would move them."""
    fonts = canvas.fonts()
    for role in ("display", "text", "medium"):
        assert fonts[role].cap_height == 0.729


def test_every_colour_role_is_a_theme_field():
    assert typing.get_args(canvas.Role) == tuple(f.name for f in fields(canvas.Theme))


def test_a_fact_too_long_for_the_about_section_stops_the_build(monkeypatch):
    facts = [("Focus", "a rather long fact " * 12), ("Daily drivers", "Python")]
    monkeypatch.setitem(build.CONFIG, "facts", facts)
    with pytest.raises(ValueError, match="'Focus' fact wraps to"):
        build.build_about(build.fonts(), build.THEMES["light"], "About")
