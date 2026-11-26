"""Activity: the live numbers on the profile, fetched from GitHub."""

import json
import re
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.client import HTTPException
from typing import Any, Protocol, TypedDict

Day = tuple[str, int, int]  # (ISO date, contributions, level 0-4)


class Repo(TypedDict):
    name: str
    description: str | None
    url: str
    stars: int
    language: str | None


@dataclass(frozen=True)
class Activity:
    """What GitHub reported. A number no source supplied is None, and the profile shows a dash."""

    contributions: int | None = None
    days: list[Day] | None = None  # oldest first
    repos: int | None = None
    stars: int | None = None
    followers: int | None = None
    languages: dict[str, int] | None = None  # {language: weight}; only the shares are drawn, see below
    work: list[Repo] | None = None

    @property
    def complete(self) -> bool:
        """Enough to redraw the profile: the calendar and the repository numbers both arrived."""
        return self.days is not None and self.repos is not None


class Transport(Protocol):
    def __call__(
        self, url: str, token: str | None = None, payload: dict | None = None, accept: str = ...
    ) -> str: ...


class ActivityUnavailable(Exception):
    """GitHub answered, but not with the numbers asked for."""


# What a failing source looks like: network or HTTP errors, a cut-off response, a body that is
# not JSON, a response missing a field, or ActivityUnavailable. Anything else is a bug and propagates.
UNAVAILABLE = (OSError, HTTPException, ValueError, LookupError, ActivityUnavailable)

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
REPO_FIELDS = "name description url stargazerCount primaryLanguage{name}"
QUERY = """query($login:String!){user(login:$login){
  followers{totalCount}
  pinnedItems(first:6,types:REPOSITORY){nodes{...on Repository{%s}}}
  repositories(ownerAffiliations:OWNER,privacy:PUBLIC,isFork:false,first:100,
               orderBy:{field:STARGAZERS,direction:DESC}){
    totalCount nodes{%s languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}}}}
  contributionsCollection{contributionCalendar{totalContributions
    weeks{contributionDays{date contributionCount contributionLevel}}}}}}""" % (REPO_FIELDS, REPO_FIELDS)  # noqa: UP031 (braces)


def http(
    url: str, token: str | None = None, payload: dict | None = None, accept: str = "application/json"
) -> str:
    headers = {"User-Agent": "profile-artwork", "Accept": accept}
    if token:
        headers["Authorization"] = f"bearer {token}"
    data = json.dumps(payload).encode() if payload else None
    with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=30) as r:
        return r.read().decode()


def pick_work(repos: list[Repo], user: str, limit: int) -> list[Repo]:
    return [r for r in repos if r["name"].lower() != user.lower()][:limit]


def add_weight(langs: dict[str, int], language: str, weight: int) -> None:
    langs[language] = langs.get(language, 0) + weight


def fetch_graphql(user: str, token: str, transport: Transport, work_limit: int) -> dict[str, Any]:
    """Everything in one query. Languages weigh bytes of code per language in each repository.
    Stars are summed over the 100 most starred repositories only (first:100), enough for this profile."""
    res = json.loads(
        transport("https://api.github.com/graphql", token, {"query": QUERY, "variables": {"login": user}})
    )
    if res.get("errors"):
        raise ActivityUnavailable(res["errors"][0].get("message"))
    u = res["data"]["user"]
    if u is None:
        raise ActivityUnavailable(f"no GitHub user {user}")

    def repo(n: dict) -> Repo:
        return Repo(
            name=n["name"],
            description=n["description"],
            url=n["url"],
            stars=n["stargazerCount"],
            language=(n["primaryLanguage"] or {}).get("name"),
        )

    nodes = u["repositories"]["nodes"]
    langs: dict[str, int] = {}
    for r in nodes:
        for e in r["languages"]["edges"]:
            add_weight(langs, e["node"]["name"], e["size"])
    pinned = [repo(n) for n in u["pinnedItems"]["nodes"] if n]
    cal = u["contributionsCollection"]["contributionCalendar"]
    return {
        "contributions": cal["totalContributions"],
        "days": [
            (d["date"], d["contributionCount"], LEVELS[d["contributionLevel"]])
            for w in cal["weeks"]
            for d in w["contributionDays"]
        ],
        "languages": langs,
        "repos": u["repositories"]["totalCount"],
        "followers": u["followers"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in nodes),
        "work": pick_work(pinned or [repo(n) for n in nodes], user, work_limit),
    }


def fetch_calendar(user: str, transport: Transport) -> dict[str, Any]:
    """The public contribution calendar: the same numbers the profile page shows."""
    page = CalendarPage()
    page.feed(transport(f"https://github.com/users/{user}/contributions", accept="text/html"))
    if not page.cells:
        raise ActivityUnavailable("no calendar cells on the page")
    days = []
    for date, cid, level in page.cells:
        # a day without contributions says "No contributions on …"
        m = re.match(r"([\d,]+) contribution", page.tips.get(cid, "").strip())
        days.append((date, int(m.group(1).replace(",", "")) if m else 0, int(level)))
    days.sort()
    return {"days": days, "contributions": sum(d[1] for d in days)}


class CalendarPage(HTMLParser):
    """Day cells (<td data-date data-level id>) and the <tool-tip for=id> text that holds each count."""

    def __init__(self) -> None:
        super().__init__()
        self.cells: list[tuple[str, str, str]] = []
        self.tips: dict[str, str] = {}
        self._tip: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "td" and "data-date" in a and "data-level" in a:
            self.cells.append((a["data-date"], a.get("id", ""), a["data-level"]))
        elif tag == "tool-tip" and "for" in a:
            self._tip = a["for"]
            self.tips[self._tip] = ""

    def handle_data(self, data: str) -> None:
        if self._tip:
            self.tips[self._tip] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "tool-tip":
            self._tip = None


def fetch_rest(user: str, token: str | None, transport: Transport, work_limit: int) -> dict[str, Any]:
    """Fallback for the repository numbers when GraphQL is unavailable. REST has no per-language
    byte counts, so each repository's size in KB counts for its primary language: the shares differ."""
    profile = json.loads(transport(f"https://api.github.com/users/{user}", token))
    repos = json.loads(transport(f"https://api.github.com/users/{user}/repos?per_page=100&type=owner", token))
    own = sorted((r for r in repos if not r["fork"]), key=lambda r: -r["stargazers_count"])
    langs: dict[str, int] = {}
    for r in own:
        if r["language"]:
            add_weight(langs, r["language"], max(r["size"], 1))
    work = [
        Repo(
            name=r["name"],
            description=r["description"],
            url=r["html_url"],
            stars=r["stargazers_count"],
            language=r["language"],
        )
        for r in own
    ]
    return {
        "repos": len(own),
        "followers": profile["followers"],
        "languages": langs,
        "stars": sum(r["stargazers_count"] for r in own),
        "work": pick_work(work, user, work_limit),
    }


def fetch_activity(user: str, token: str | None, transport: Transport, *, work_limit: int) -> Activity:
    """The profile's Activity, merged from three sources, each of which may fail:
    GraphQL when there is a token, else (or when it fails) the REST API, for the repository numbers;
    then the public calendar, whose days and total replace GraphQL's because they match the profile page;
    if the calendar fails, GraphQL's days and total stay.

    transport(url, token=None, payload=None, accept=...) -> response text; `http` in production.
    work_limit caps the selected work, which never includes the profile repository itself."""
    fields: dict[str, Any] = {}
    if token:
        try:
            fields = fetch_graphql(user, token, transport, work_limit)
        except UNAVAILABLE as exc:
            print(f"  GraphQL failed ({exc}); falling back to the REST API")
    if not fields:
        try:
            fields = fetch_rest(user, token, transport, work_limit)
        except UNAVAILABLE as exc:  # unauthenticated rate limits are common
            print(f"  REST API unavailable ({exc}); repository numbers left blank")
    try:
        fields.update(fetch_calendar(user, transport))
    except UNAVAILABLE as exc:
        print(f"  public calendar unavailable ({exc})")
    return Activity(**fields)
