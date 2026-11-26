"""fetch_activity merges GitHub's sources; a fake transport answers from tests/fixtures/github/."""
import urllib.error
from pathlib import Path

import pytest

from activity import Activity, fetch_activity

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "github"
USER = "FilipTw"
GRAPHQL = "https://api.github.com/graphql"
CALENDAR = f"https://github.com/users/{USER}/contributions"
REST_USER = f"https://api.github.com/users/{USER}"
REST_REPOS = f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner"

CALENDAR_DAYS = [
    ("2026-06-07", 0, 0), ("2026-06-08", 0, 0), ("2026-06-09", 0, 0), ("2026-06-10", 22, 2),
    ("2026-06-11", 39, 3), ("2026-06-12", 10, 1), ("2026-06-13", 20, 2), ("2026-06-14", 17, 2),
    ("2026-06-15", 17, 2), ("2026-06-16", 27, 2), ("2026-06-17", 11, 1), ("2026-06-18", 5, 1),
    ("2026-06-19", 2, 1), ("2026-06-20", 0, 0), ("2026-06-21", 7, 1), ("2026-06-22", 9, 1),
    ("2026-06-23", 2, 1), ("2026-06-24", 9, 1), ("2026-06-25", 4, 1), ("2026-06-26", 10, 1),
    ("2026-06-27", 1, 1),
]
FROM_CALENDAR = {"days": CALENDAR_DAYS, "contributions": 212}
FROM_GRAPHQL = {
    "contributions": 3,
    "days": [("2026-06-14", 1, 1), ("2026-06-15", 2, 2)],
    "languages": {"Python": 3500, "Shell": 200},
    "repos": 3,
    "followers": 12,
    "stars": 6,
    "work": [{"name": "tiny-agent", "description": None, "url": "https://github.com/FilipTw/tiny-agent",
              "stars": 0, "language": None}],
}
FROM_REST = {
    "repos": 3,
    "followers": 11,
    "languages": {"Python": 120, "TeX": 1},
    "stars": 5,
    "work": [{"name": "contour-lab", "description": "Loss landscapes as contour maps.",
              "url": "https://github.com/FilipTw/contour-lab", "stars": 4, "language": "Python"},
             {"name": "notes", "description": None, "url": "https://github.com/FilipTw/notes",
              "stars": 0, "language": "TeX"}],
}


def offline(url):
    raise urllib.error.URLError(f"no route to {url}")


def fake_github(**override):
    """A transport that answers like GitHub. override maps a URL to its text, or to a callable that raises."""
    answers = {GRAPHQL: (FIXTURES / "graphql.json").read_text(),
               CALENDAR: (FIXTURES / "contributions.html").read_text(),
               REST_USER: (FIXTURES / "rest_user.json").read_text(),
               REST_REPOS: (FIXTURES / "rest_repos.json").read_text()}
    answers.update({{"graphql": GRAPHQL, "calendar": CALENDAR, "rest": REST_REPOS}[k]: v for k, v in override.items()})

    def transport(url, token=None, payload=None, accept="application/json"):
        if url == GRAPHQL and not token:
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
        answer = answers[url]
        return answer(url) if callable(answer) else answer
    return transport


def fetch(token, transport):
    return fetch_activity(USER, token, transport, work_limit=4)


def test_with_a_token_graphql_supplies_the_numbers_and_the_public_calendar_the_days():
    assert fetch("token", fake_github()) == Activity(**{**FROM_GRAPHQL, **FROM_CALENDAR})


@pytest.mark.parametrize("graphql", [offline, '{"errors": [{"message": "rate limited"}]}'],
                         ids=["network", "graphql-error"])
def test_when_graphql_fails_the_rest_api_supplies_the_numbers(graphql):
    assert fetch("token", fake_github(graphql=graphql)) == Activity(**{**FROM_REST, **FROM_CALENDAR})


def test_without_a_token_the_rest_api_supplies_the_numbers():
    assert fetch(None, fake_github()) == Activity(**{**FROM_REST, **FROM_CALENDAR})


def test_when_the_rest_api_fails_too_only_the_calendar_is_known():
    assert fetch(None, fake_github(rest=offline)) == Activity(**FROM_CALENDAR)


def test_when_the_calendar_fails_the_graphql_days_stay():
    assert fetch("token", fake_github(calendar=offline)) == Activity(**FROM_GRAPHQL)
