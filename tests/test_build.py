"""Characterization test: the whole profile, built from fixed inputs, must match tests/golden/."""
import datetime as dt
import json
import shutil
import types
from pathlib import Path

import pytest

import build

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
TODAY = dt.date(2026, 6, 15)
BRANCH = "main"


class FixedDate(dt.date):
    @classmethod
    def today(cls):
        return TODAY


@pytest.fixture
def activity():
    return json.loads((HERE / "fixtures" / "activity.json").read_text())


def build_files(tmp_path, monkeypatch, activity):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "OUT", tmp_path / "assets")
    monkeypatch.setattr(build, "dt", types.SimpleNamespace(date=FixedDate))
    monkeypatch.setattr(build, "fetch_activity", lambda user: activity)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("GITHUB_REF_NAME", BRANCH)
    build.main()
    return {p.relative_to(tmp_path).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(tmp_path.rglob("*")) if p.is_file()}


def test_profile_matches_golden(tmp_path, monkeypatch, activity, request):
    files = build_files(tmp_path, monkeypatch, activity)
    if request.config.getoption("--update-golden"):
        shutil.rmtree(GOLDEN, ignore_errors=True)
        for path, text in files.items():
            (GOLDEN / path).parent.mkdir(parents=True, exist_ok=True)
            (GOLDEN / path).write_text(text, encoding="utf-8")
        pytest.skip("golden files updated")
    golden = {p.relative_to(GOLDEN).as_posix(): p.read_text(encoding="utf-8")
              for p in sorted(GOLDEN.rglob("*")) if p.is_file()}
    assert sorted(files) == sorted(golden)
    for path in golden:
        assert files[path] == golden[path], f"{path} differs from tests/golden/{path}"
