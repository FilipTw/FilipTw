"""Activity: the live numbers on the profile, fetched from GitHub."""
import json
import re
import urllib.request

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


def pick_work(repos, user, limit):
    repos = [r for r in repos if r["name"].lower() != user.lower()]
    return repos[:limit]


def fetch_graphql(user, token, transport, work_limit):
    res = json.loads(transport("https://api.github.com/graphql", token,
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
        "work": pick_work(pinned or [repo(n) for n in u["repositories"]["nodes"]], user, work_limit),
    }


def fetch_calendar(user, transport):
    """The public contribution calendar: the same numbers the profile page shows."""
    page = transport(f"https://github.com/users/{user}/contributions", accept="text/html")
    cells = re.findall(r'data-date="(\d{4}-\d\d-\d\d)" id="([\w-]+)" data-level="(\d)"', page)
    if not cells:
        raise RuntimeError("no calendar cells on the page")
    tips = dict(re.findall(r'for="([\w-]+)"[^>]*>([^<]*)</tool-tip>', page))
    days = []
    for date, cid, level in cells:
        m = re.match(r"([\d,]+) contribution", tips.get(cid, ""))
        days.append((date, int(m.group(1).replace(",", "")) if m else 0, int(level)))
    days.sort()
    return {"days": days, "contributions": sum(d[1] for d in days)}


def fetch_rest(user, token, transport, work_limit):
    """Fallback for the repository numbers when GraphQL is unavailable."""
    profile = json.loads(transport(f"https://api.github.com/users/{user}", token))
    repos = json.loads(transport(f"https://api.github.com/users/{user}/repos?per_page=100&type=owner", token))
    own = sorted((r for r in repos if not r["fork"]), key=lambda r: -r["stargazers_count"])
    langs = {}
    for r in own:
        if r["language"]:
            langs[r["language"]] = langs.get(r["language"], 0) + max(r["size"], 1)
    return {
        "repos": len(own), "followers": profile["followers"], "languages": langs,
        "stars": sum(r["stargazers_count"] for r in own),
        "work": pick_work([{"name": r["name"], "description": r["description"], "url": r["html_url"],
                            "stars": r["stargazers_count"], "language": r["language"]} for r in own],
                          user, work_limit),
    }


def fetch_activity(user, token, transport, *, work_limit):
    activity = {}
    if token:
        try:
            activity = fetch_graphql(user, token, transport, work_limit)
        except Exception as exc:
            print(f"  GraphQL failed ({exc}); falling back to the REST API")
    if not activity:
        try:
            activity = fetch_rest(user, token, transport, work_limit)
        except Exception as exc:  # unauthenticated rate limits are common
            print(f"  REST API unavailable ({exc}); repository numbers left blank")
    try:
        activity.update(fetch_calendar(user, transport))
    except Exception as exc:
        print(f"  public calendar unavailable ({exc})")
    return activity
