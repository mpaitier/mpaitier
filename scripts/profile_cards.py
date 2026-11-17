"""Génère les cartes SVG du profil (projets, stats, langages) à partir de l'API GitHub.

Lancé par la GitHub Action .github/workflows/profile.yml, qui publie le résultat
sur la branche `output`. En local : `python scripts/profile_cards.py --mock dist`.
"""
import json
import os
import random
import sys
import textwrap
import urllib.request
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "mpaitier")
ACTIVITY_DAYS = 60
PINNED = ["amor_app", "cartodex", "ThristyQuest", "quarter-bells"]
# Nom affiché sur la carte quand il diffère du nom du dépôt
DISPLAY_NAMES = {"ThristyQuest": "ThirstyQuest"}
# Langages générés automatiquement par Flutter/Android (dossiers runner), exclus du classement
EXCLUDED_LANGS = {"CMake", "Swift", "Objective-C", "Ruby", "HTML", "C", "Batchfile",
                  "Shell", "Dockerfile", "PowerShell", "Makefile", "CSS"}

RED, BLACK, WHITE, GREY = "#FF0022", "#0D0D0D", "#F5F5F5", "#9A9A9A"
FONT = "'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"
FONT_BOLD = "'Arial Black', 'Segoe UI Black', 'Helvetica Neue', Arial, sans-serif"


# ---------------------------------------------------------------- API GitHub
def api(url, payload=None):
    token = os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": f"{USER}-profile-cards"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    pullRequests { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


REPO_FIELDS = """
  name nameWithOwner description stargazerCount forkCount
  repositoryTopics(first: 3) { nodes { topic { name } } }
  languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
"""


def fetch_repos():
    """Récupère les dépôts de PINNED en une requête. Un dépôt introuvable est signalé, pas bloquant."""
    parts = []
    for i, entry in enumerate(PINNED):
        owner, name = entry.split("/", 1) if "/" in entry else (USER, entry)
        parts.append(f'r{i}: repository(owner: "{owner}", name: "{name}") {{ {REPO_FIELDS} }}')
    res = api("https://api.github.com/graphql", {"query": "query {" + " ".join(parts) + "}"})
    for err in res.get("errors", []):
        print(f"::warning::{err.get('message')}")
    data = res.get("data") or {}
    repos = []
    for i, entry in enumerate(PINNED):
        r = data.get(f"r{i}")
        if r is None:
            print(f"::warning::Dépôt introuvable ou privé : {entry} (carte ignorée)")
            continue
        langs = [e["node"]["name"] for e in r["languages"]["edges"]]
        main_lang = next((l for l in langs if l not in EXCLUDED_LANGS), langs[0] if langs else None)
        repos.append({"name": r["name"], "title": DISPLAY_NAMES.get(r["name"], r["name"]), "description": r["description"] or "",
                      "language": main_lang, "stars": r["stargazerCount"], "forks": r["forkCount"],
                      "topics": [n["topic"]["name"] for n in r["repositoryTopics"]["nodes"]]})
    return repos


def fetch():
    res = api("https://api.github.com/graphql", {"query": QUERY, "variables": {"login": USER}})
    if res.get("errors"):
        raise SystemExit(f"Erreur GraphQL : {res['errors']}")
    user = res["data"]["user"]
    repos = fetch_repos()

    lang_sizes, lang_colors, stars = {}, {}, 0
    for node in user["repositories"]["nodes"]:
        stars += node["stargazerCount"]
        for e in node["languages"]["edges"]:
            n = e["node"]["name"]
            if n in EXCLUDED_LANGS:
                continue
            lang_sizes[n] = lang_sizes.get(n, 0) + e["size"]
            lang_colors[n] = e["node"]["color"] or GREY
    cc = user["contributionsCollection"]
    stats = {
        "contributions": cc["contributionCalendar"]["totalContributions"],
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "prs": user["pullRequests"]["totalCount"],
        "stars": stars,
        "repos": user["repositories"]["totalCount"],
        "followers": user["followers"]["totalCount"],
    }
    days = [(d["date"], d["contributionCount"])
            for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    stats["days"] = days[-ACTIVITY_DAYS:]
    return repos, stats, lang_sizes


def mock():
    repos = [
        {"name": "amor_app", "language": "Dart", "stars": 1, "forks": 0, "topics": ["flutter", "firebase"],
         "description": "Journal de souvenirs pour les couples, en Flutter et Firebase. Chaque membre de la relation ajoute des souvenirs (photos, lieu, GIF), les dates qui comptent, et tout le monde voit les ajouts des autres."},
        {"name": "cartodex", "language": "Dart", "stars": 0, "forks": 0, "topics": ["flutter", "bloc"],
         "description": "Application Flutter de suivi de collection Pokémon TCG Pocket sur plusieurs comptes : progression par set, boosters à ouvrir en priorité, synchronisation Firebase."},
        {"name": "ThirstyQuest", "language": "Kotlin", "stars": 1, "forks": 0, "topics": [], "description": ""},
        {"name": "quarter-bells", "language": "TypeScript", "stars": 0, "forks": 0, "topics": [],
         "description": "Quarter Bells est un jeu coopératif en ligne pour 2 à 4 joueurs."},
    ]
    rnd = random.Random(1)
    import datetime
    start = datetime.date(2026, 11, 17) - datetime.timedelta(days=ACTIVITY_DAYS - 1)
    days = [((start + datetime.timedelta(days=i)).isoformat(),
             max(0, int(rnd.gauss(4, 5))) if rnd.random() > .3 else 0) for i in range(ACTIVITY_DAYS)]
    stats = {"days": days, "contributions": 564, "commits": 498, "prs": 61, "stars": 3, "repos": 21, "followers": 5}
    langs = {"Dart": 900000, "Kotlin": 260000, "TypeScript": 120000, "C#": 90000,
             "Python": 70000, "C++": 40000, "JavaScript": 30000}
    return repos, stats, langs


# ---------------------------------------------------------------- dessin
LANG_COLORS = {"Dart": "#00B4AB", "Kotlin": "#A97BFF", "TypeScript": "#3178C6", "C#": "#178600",
               "Python": "#3572A5", "C++": "#F34B7D", "JavaScript": "#F1E05A", "Java": "#B07219",
               "GDScript": "#355570"}

CSS = f"""<style>
  .t {{ font: 800 20px {FONT_BOLD}; fill: {WHITE}; letter-spacing: .5px; }}
  .d {{ font: 400 13.5px {FONT}; fill: {WHITE}; }}
  .m {{ font: 600 12.5px {FONT}; fill: {GREY}; }}
  .k {{ font: 800 12px {FONT_BOLD}; fill: {RED}; letter-spacing: 1px; }}
  .v {{ font: 800 26px {FONT_BOLD}; fill: {WHITE}; }}
  .tag {{ font: 700 11px {FONT}; fill: {BLACK}; }}
  .in {{ animation: in .6s ease-out both; }}
  @keyframes in {{ from {{ opacity: 0; transform: translateX(-12px); }} to {{ opacity: 1; transform: none; }} }}
</style>"""

DEFS = f"""<defs>
  <pattern id="dots" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(30)">
    <circle cx="5" cy="5" r="1.4" fill="{RED}" opacity=".35"/>
  </pattern>
  <pattern id="stripes" width="24" height="24" patternUnits="userSpaceOnUse" patternTransform="rotate(-35)">
    <rect width="12" height="24" fill="{BLACK}" opacity=".25"/>
  </pattern>
</defs>"""


def frame(w, h, title, seed):
    """Fond noir découpé en biais, trame rouge, bandeau de titre penché."""
    rnd = random.Random(seed)
    tw = len(title) * 13.5 + 40
    shard = (f'<polygon points="{w - rnd.randint(60, 110)},0 {w},0 {w},{rnd.randint(40, 70)}" fill="{RED}"/>'
             f'<polygon points="{w - 18},{h - 46} {w},{h - 62} {w},{h - 30}" fill="{WHITE}"/>')
    return (f'<polygon points="0,6 {w},0 {w},{h - 4} 0,{h}" fill="{BLACK}"/>'
            f'<polygon points="0,6 {w * .45},3 {w * .3},{h} 0,{h}" fill="url(#dots)"/>'
            f'{shard}'
            f'<g transform="translate(14 14) skewX(-14)">'
            f'<rect x="4" y="4" width="{tw}" height="34" fill="{WHITE}"/>'
            f'<rect width="{tw}" height="34" fill="{RED}"/><rect width="{tw}" height="34" fill="url(#stripes)"/>'
            f'<text x="16" y="24" class="t">{escape(title)}</text></g>')


def svg(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'{CSS}{DEFS}{body}</svg>')


def star_icon(x, y):
    return (f'<path transform="translate({x} {y}) scale(.75)" fill="{RED}" '
            f'd="M8 .25l2.5 5 5.5.8-4 3.9.95 5.5L8 12.9l-4.95 2.55L4 9.95 0 6.05l5.5-.8z"/>')


def fork_icon(x, y):
    return (f'<g transform="translate({x} {y})" fill="none" stroke="{RED}" stroke-width="1.8">'
            f'<circle cx="3" cy="2.5" r="2"/><circle cx="11" cy="2.5" r="2"/><circle cx="7" cy="12" r="2"/>'
            f'<path d="M3 4.5v1.5q0 2 2 2h4q2 0 2-2V4.5M7 8v2"/></g>')


def project_card(repo, seed):
    w, h = 420, 165
    desc = repo["description"] or "Projet en cours, description à venir."
    lines = textwrap.wrap(desc, 56)[:3]
    if len(textwrap.wrap(desc, 56)) > 3:
        lines[-1] = lines[-1][:53].rstrip() + "…"
    body = frame(w, h, repo.get("title", repo["name"]), seed)
    body += "".join(f'<text x="22" y="{74 + i * 19}" class="d in" style="animation-delay:{.1 * i:.1f}s">'
                    f'{escape(l)}</text>' for i, l in enumerate(lines))
    y = h - 18
    x = 22
    lang = repo["language"]
    if lang:
        body += f'<circle cx="{x + 6}" cy="{y - 4}" r="6" fill="{LANG_COLORS.get(lang, GREY)}" stroke="{WHITE}" stroke-width="1.2"/>'
        body += f'<text x="{x + 18}" y="{y}" class="m">{escape(lang)}</text>'
        x += 30 + len(lang) * 7.5
    body += star_icon(x, y - 11) + f'<text x="{x + 16}" y="{y}" class="m">{repo["stars"]}</text>'
    x += 42
    body += fork_icon(x, y - 12) + f'<text x="{x + 18}" y="{y}" class="m">{repo["forks"]}</text>'
    x += 46
    for t in repo["topics"]:
        tw = len(t) * 6.6 + 14
        if x + tw > w - 30:
            break
        body += (f'<g transform="translate({x} {y - 14}) skewX(-12)"><rect width="{tw}" height="18" fill="{WHITE}"/>'
                 f'<text x="7" y="13" class="tag">{escape(t)}</text></g>')
        x += tw + 6
    return svg(w, h, body)


def stats_card(stats):
    w, h = 420, 215
    items = [("CONTRIBUTIONS · 12 MOIS", stats["contributions"]), ("COMMITS · 12 MOIS", stats["commits"]),
             ("PULL REQUESTS", stats["prs"]), ("DÉPÔTS PUBLICS", stats["repos"]),
             ("ÉTOILES", stats["stars"]), ("FOLLOWERS", stats["followers"])]
    body = frame(w, h, "STATS", 41)
    for i, (k, v) in enumerate(items):
        col, row = i % 2, i // 2
        x, y = 30 + col * 200, 80 + row * 48
        body += (f'<g class="in" style="animation-delay:{.08 * i:.2f}s">'
                 f'<polygon points="{x - 8},{y - 12} {x - 3},{y - 12} {x - 9},{y + 18} {x - 14},{y + 18}" fill="{RED}"/>'
                 f'<text x="{x}" y="{y}" class="k">{k}</text>'
                 f'<text x="{x}" y="{y + 26}" class="v">{v}</text></g>')
    return svg(w, h, body)


def langs_card(lang_sizes):
    w, h = 420, 215
    top = sorted(lang_sizes.items(), key=lambda kv: -kv[1])[:6]
    total = sum(s for _, s in top) or 1
    body = frame(w, h, "LANGAGES", 77)
    # barre segmentée penchée
    x, bar_w = 24, w - 48
    body += f'<g transform="translate(0 64) skewX(-20)">'
    for name, size in top:
        seg = bar_w * size / total
        body += f'<rect x="{x:.1f}" width="{max(seg - 2, 1):.1f}" height="14" fill="{LANG_COLORS.get(name, GREY)}"/>'
        x += seg
    body += "</g>"
    for i, (name, size) in enumerate(top):
        col, row = i % 2, i // 2
        lx, ly = 30 + col * 200, 112 + row * 28
        body += (f'<g class="in" style="animation-delay:{.08 * i:.2f}s">'
                 f'<polygon points="{lx + 3},{ly - 11} {lx + 15},{ly - 11} {lx + 12},{ly + 1} {lx},{ly + 1}" '
                 f'fill="{LANG_COLORS.get(name, GREY)}" stroke="{WHITE}" stroke-width="1"/>'
                 f'<text x="{lx + 22}" y="{ly}" class="d">{escape(name)}</text>'
                 f'<text x="{lx + 160}" y="{ly}" class="m" text-anchor="end">{100 * size / total:.1f} %</text></g>')
    return svg(w, h, body)


MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def activity_card(days):
    w, h = 860, 260
    left, right, top, bottom = 56, 24, 70, 44
    pw, ph = w - left - right, h - top - bottom
    vmax = max(max(c for _, c in days), 1)
    n = len(days)
    pts = [(left + pw * i / (n - 1), top + ph - ph * c / vmax) for i, (_, c) in enumerate(days)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{left},{top + ph} {line} {left + pw},{top + ph}"
    body = frame(w, h, f"ACTIVITÉ · {n} DERNIERS JOURS", 13)
    # grille horizontale
    for i in range(5):
        y = top + ph * i / 4
        val = round(vmax * (1 - i / 4))
        body += (f'<line x1="{left}" x2="{left + pw}" y1="{y:.1f}" y2="{y:.1f}" stroke="{WHITE}" stroke-opacity=".08"/>'
                 f'<text x="{left - 10}" y="{y + 4:.1f}" class="m" text-anchor="end">{val}</text>')
    # repères de dates (tous les 10 jours)
    for i in range(0, n, 10):
        d = days[i][0]
        label = f"{int(d[8:10])} {MONTHS[int(d[5:7]) - 1]}"
        body += f'<text x="{pts[i][0]:.1f}" y="{h - 16}" class="m" text-anchor="middle">{label}</text>'
    body += (f'<polygon points="{area}" fill="{RED}" fill-opacity=".28"/>'
             f'<polygon points="{area}" fill="url(#stripes)"/>'
             f'<polyline points="{line}" fill="none" stroke="{RED}" stroke-width="3" stroke-linejoin="bevel"/>')
    best = max(range(n), key=lambda i: days[i][1])
    for i, (x, y) in enumerate(pts):
        if days[i][1] > 0:
            body += f'<rect x="{x - 3:.1f}" y="{y - 3:.1f}" width="6" height="6" fill="{WHITE}" transform="rotate(45 {x:.1f} {y:.1f})"/>'
    bx, by = pts[best]
    body += (f'<g transform="translate({min(bx, w - 120):.1f} {max(by - 30, top - 8):.1f}) skewX(-12)">'
             f'<rect width="96" height="20" fill="{WHITE}"/>'
             f'<text x="8" y="14" class="tag">RECORD : {days[best][1]}</text></g>')
    return svg(w, h, body)


def main():
    args = sys.argv[1:]
    use_mock = "--mock" in args
    out = next(a for a in args if not a.startswith("--"))
    os.makedirs(out, exist_ok=True)
    repos, stats, langs = mock() if use_mock else fetch()
    for i, repo in enumerate(repos):
        with open(os.path.join(out, f"card-{repo['name']}.svg"), "w", encoding="utf-8") as f:
            f.write(project_card(repo, i * 7 + 3))
    with open(os.path.join(out, "card-stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_card(stats))
    with open(os.path.join(out, "card-langs.svg"), "w", encoding="utf-8") as f:
        f.write(langs_card(langs))
    with open(os.path.join(out, "card-activity.svg"), "w", encoding="utf-8") as f:
        f.write(activity_card(stats["days"]))
    print(f"{len(repos) + 3} cartes générées dans {out}")


if __name__ == "__main__":
    main()
