"""Builds the animated profile card (dark_mode.svg + light_mode.svg).

Left: an ASCII portrait (portrait.json, brightness levels 0-8 per character cell) that draws in
row by row with a light sweeping through it. Right: a terminal-style info card whose lines type in.
GitHub stats are fetched live when GITHUB_TOKEN is set; otherwise the last values in stats.json are reused.

Standard library only, so it runs on GitHub Actions without installing anything.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).parent
LOGIN = "Nanichowdary04"
WIDTH = 60  # characters in the info card

INFO = [
    ("header", "navaneeth@bethini"),
    ("kv", "OS", "Windows 11, Android"),
    ("kv", "Host", "Malla Reddy University, Hyderabad"),
    ("kv", "Kernel", "B.Tech CSE · 2025 – 2029"),
    ("kv", "Role", "Creative Developer / AI Engineer"),
    ("blank",),
    ("kv", "Languages.Programming", "Python, C++, Java, JavaScript"),
    ("kv", "Languages.Web", "TypeScript, React, HTML, CSS"),
    ("kv", "Languages.Backend", "Flask, SQLite"),
    ("blank",),
    ("kv", "Interests", "AI, Cybersecurity, Game Dev"),
    ("kv", "Goal", "F1 Telemetry Engineering"),
    ("kv", "Building", "CINEMAX, RamGuard, ZENO, WiFiX"),
    ("kv", "Hackathons", "MASQUERADE '26 — Winner"),
    ("blank",),
    ("section", "Contact"),
    ("kv", "Email", "navaneethbethini004@gmail.com"),
    ("kv", "LinkedIn", "linkedin.com/in/navaneeth-bethini-381a94377"),
    ("kv", "Portfolio", "nanichowdary04.github.io"),
    ("blank",),
    ("section", "GitHub Stats"),
    ("stats",),
    ("blank",),
    ("prompt",),
]

THEMES = {
    "dark": {
        "bg": "#161b22", "text": "#c9d1d9", "key": "#ffa657", "value": "#a5d6ff", "dots": "#616e7f",
        "ascii": "#b1bac4", "shine": "#58a6ff", "ramp": ".:-=+*#%@",  # darker photo → denser glyph
        "dense_is_bright": False,
    },
    "light": {
        "bg": "#f6f8fa", "text": "#24292f", "key": "#953800", "value": "#0a3069", "dots": "#c2cfde",
        "ascii": "#424a53", "shine": "#0969da", "ramp": ".:-=+*#%@",  # darker photo → denser glyph
        "dense_is_bright": False,
    },
}

FONT = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"


# ---------------------------------------------------------------- GitHub stats
def graphql(query: str, token: str) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-card-builder"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def fetch_stats(token: str) -> dict:
    base = graphql(
        """{ user(login: "%s") {
            createdAt
            followers { totalCount }
            repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) {
              totalCount nodes { stargazerCount } }
            repositoriesContributedTo(first: 1, includeUserRepositories: false,
              contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY, PULL_REQUEST_REVIEW]) { totalCount }
            contributionsCollection { contributionCalendar { totalContributions } }
        } }""" % LOGIN,
        token,
    )["user"]
    # all-time commits: one contributions window per calendar year since the account was created
    start = int(base["createdAt"][:4])
    now = dt.datetime.now(dt.timezone.utc)
    parts = []
    for y in range(start, now.year + 1):
        end = f"{y}-12-31T23:59:59Z" if y < now.year else now.strftime("%Y-%m-%dT%H:%M:%SZ")
        parts.append(f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{end}") '
                     "{ totalCommitContributions restrictedContributionsCount }")
    years = graphql('{ user(login: "%s") { %s } }' % (LOGIN, " ".join(parts)), token)["user"]
    commits = sum(v["totalCommitContributions"] for v in years.values())
    return {
        "repos": base["repositories"]["totalCount"],
        "contributed": base["repositoriesContributedTo"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in base["repositories"]["nodes"]),
        "followers": base["followers"]["totalCount"],
        "commits": commits,
        "contributions": base["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "updated": now.strftime("%Y-%m-%d"),
    }


def load_stats() -> dict:
    cache = ROOT / "stats.json"
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        try:
            stats = fetch_stats(token)
            cache.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
            return stats
        except Exception as exc:  # keep the card building even if the API hiccups
            print("stats fetch failed, using cache:", exc)
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    return {"repos": 0, "contributed": 0, "stars": 0, "followers": 0, "commits": 0, "contributions": 0, "updated": ""}


# ---------------------------------------------------------------- text lines
def kv_parts(key: str, value: str, width: int = WIDTH) -> list[tuple[str, str]]:
    """'. Key: ....... value' as coloured segments, padded with dots to a fixed width."""
    head = f". {key}:"
    dots = max(2, width - len(head) - len(value) - 2)
    return [("cc", ". "), ("key", key), ("text", ":"), ("cc", " " + "." * dots + " "), ("value", value)]


def pair_parts(k1: str, v1: str, k2: str, v2: str) -> list[tuple[str, str]]:
    """Two key/value pairs on one line separated by '|'."""
    half = (WIDTH - 3) // 2
    a, b = kv_parts(k1, v1, half), kv_parts(k2, v2, WIDTH - half - 3)
    b[0] = ("cc", "")  # drop the second leading '. '
    return a + [("text", " | ")] + b


def info_lines(stats: dict) -> list[list[tuple[str, str]]]:
    out: list[list[tuple[str, str]]] = []
    for item in INFO:
        kind = item[0]
        if kind == "header":
            out.append([("text", item[1]), ("cc", " " + "—" * (WIDTH - len(item[1]) - 1))])
        elif kind == "section":
            label = f"- {item[1]} "
            out.append([("text", label), ("cc", "—" * (WIDTH - len(label)))])
        elif kind == "kv":
            out.append(kv_parts(item[1], item[2]))
        elif kind == "blank":
            out.append([])
        elif kind == "stats":
            out.append(pair_parts("Repos", f"{stats['repos']} {{Contributed: {stats['contributed']}}}", "Stars", str(stats["stars"])))
            out.append(pair_parts("Commits", f"{stats['commits']:,}", "Followers", str(stats["followers"])))
            out.append(kv_parts("Contributions (last year)", f"{stats['contributions']:,}"))
        elif kind == "prompt":
            out.append([("value", "navaneeth@bethini"), ("text", ":"), ("key", "~"), ("text", "$ "), ("cursor", "▋")])
    return out


# ---------------------------------------------------------------- SVG
def render(theme: str, stats: dict) -> str:
    t = THEMES[theme]
    art = json.loads((ROOT / "portrait.json").read_text(encoding="utf-8"))
    ramp = t["ramp"]
    rows = []
    for row in art["grid"]:
        chars = []
        for ch in row:
            if ch == " ":
                chars.append(" ")
            else:
                level = int(ch)  # 0 = darkest … 8 = brightest
                chars.append(ramp[level] if t["dense_is_bright"] else ramp[8 - level])
        rows.append("".join(chars))

    lines = info_lines(stats)
    fs, lh_info = 14, 20
    art_fs, lh_art = art.get("font_size", 14), art.get("line_height", 17)
    art_x, art_y = 16, 30
    info_x, info_y = 476, 34
    height = max(art_y + len(rows) * lh_art, info_y + len(lines) * lh_info) + 16
    width = 990

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'font-family="{FONT}" font-size="{fs}px">',
        "<style>",
        f".bg{{fill:{t['bg']}}} .text{{fill:{t['text']}}} .key{{fill:{t['key']}}} .value{{fill:{t['value']}}} .cc{{fill:{t['dots']}}} .cursor{{fill:{t['key']}}}",
        # each dot falls in from above with a little drift and settles (a soft overshoot on landing)
        ".d{opacity:0;animation:land .9s cubic-bezier(.2,.85,.3,1.25) forwards}",
        ".ln{opacity:0;animation:type .55s steps(24,end) forwards}",
        ".cursor{animation:blink 1s steps(1,end) infinite}",
        "@keyframes land{0%{opacity:0;transform:translate(var(--dx),-46px)}55%{opacity:1}100%{opacity:1;transform:translate(0,0)}}",
        "@keyframes type{from{opacity:1;clip-path:inset(0 100% 0 0)}to{opacity:1;clip-path:inset(0 0 0 0)}}",
        "@keyframes blink{50%{opacity:0}}",
        "@media (prefers-reduced-motion:reduce){.d,.ln{animation:none;opacity:1}.cursor{animation:none}}",
        "</style>",
        "<defs>",
        # a band of light that sweeps down through the dotted portrait, forever
        f'<linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="{height}">',
        f'<stop offset="0" stop-color="{t["ascii"]}"/><stop offset="0.40" stop-color="{t["ascii"]}"/>',
        f'<stop offset="0.5" stop-color="{t["shine"]}"/>',
        f'<stop offset="0.60" stop-color="{t["ascii"]}"/><stop offset="1" stop-color="{t["ascii"]}"/>',
        f'<animateTransform attributeName="gradientTransform" type="translate" from="0 -{height}" to="0 {height}" '
        'dur="6s" begin="1.8s" repeatCount="indefinite"/>',
        "</linearGradient>",
        "</defs>",
        f'<rect class="bg" width="{width}" height="{height}" rx="15"/>',
        f'<g fill="url(#shine)" font-size="{art_fs}px">',
    ]
    # One element per dot so each can land on its own; positions come from the grid, not the font,
    # so the picture stays aligned whatever monospace font the viewer has.
    cw = art.get("char_width", art_fs * 0.6)
    rng = random.Random(7)
    n_rows = len(rows)
    for r, row in enumerate(rows):
        for c, glyph in enumerate(row):
            if glyph == " ":
                continue
            delay = 0.15 + (r / n_rows) * 1.7 + rng.uniform(0, 0.4)
            dx = rng.uniform(-10, 10)
            out.append(f'<text class="d" x="{art_x + c * cw:.1f}" y="{art_y + r * lh_art}" '
                       f'style="animation-delay:{delay:.2f}s;--dx:{dx:.0f}px">{escape(glyph)}</text>')
    out.append("</g>")
    for i, segs in enumerate(lines):
        if not segs:
            continue
        spans = "".join(f'<tspan class="{cls}">{escape(txt).replace(" ", " ")}</tspan>' for cls, txt in segs if txt)
        delay = 0.35 + i * 0.07
        out.append(f'<text class="ln" x="{info_x}" y="{info_y + i * lh_info}" xml:space="preserve" '
                   f'style="animation-delay:{delay:.2f}s">{spans}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    stats = load_stats()
    for theme in THEMES:
        (ROOT / f"{theme}_mode.svg").write_text(render(theme, stats), encoding="utf-8")
    print("built dark_mode.svg + light_mode.svg", stats)


if __name__ == "__main__":
    main()
