"""Öffentlicher MCP-Server für Glossagens (Streamable HTTP).

Lesen: Kommentar und Rechtsprechung aus dem Repo.
Schreiben: ausschliesslich Anregungen als GitHub-Issue (Kanal A). Alles Weitere
läuft wie gehabt durch Queue und Verifikation; es gibt bewusst kein Merge-Tool.
"""
import os
import re
import time
from collections import defaultdict, deque

import requests
from mcp.server.fastmcp import Context, FastMCP

import github_client as gh

mcp = FastMCP(
    "glossagens",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8001")),
    instructions=(
        "Glossagens ist ein öffentlicher juristischer Gesetzeskommentar (Schweizer Recht). "
        "Artikel lesen mit get_article / get_case_law, Anregungen einreichen mit submit_suggestion. "
        "Anregungen werden vom Agenten geprüft und nicht sofort veröffentlicht."
    ),
)

LAW_RE = re.compile(r"^[a-z0-9-]{1,20}$")
SUBMIT_LIMIT = int(os.getenv("MCP_SUBMIT_LIMIT", "5"))  # pro Stunde und Client
SUBMIT_WINDOW = 3600
_submissions: dict[str, deque] = defaultdict(deque)
_cache: dict[str, tuple[float, object]] = {}
CACHE_TTL = 300

SUGGESTION_TYPES = [
    "Inhaltliche Korrektur",
    "Fehlende Rechtsprechung",
    "Neuer Artikel",
    "Gesetzesänderung",
    "Sonstiges",
]


def _cached(key: str, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    value = fn()
    _cache[key] = (time.time(), value)
    return value


def _law(gesetz: str) -> str:
    g = gesetz.strip().lower()
    if not LAW_RE.match(g):
        raise ValueError("Ungültiges Gesetzeskürzel (z.B. 'or', 'zgb', 'stpo').")
    return g


def _nr(nr: int) -> str:
    if not 1 <= nr <= 9999:
        raise ValueError("Ungültige Artikelnummer.")
    return f"art-{nr:03d}"


def _read(path: str) -> str:
    try:
        return _cached(path, lambda: gh.get_file(path)[0])
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise ValueError("Nicht gefunden. Kommentar zu diesem Artikel existiert (noch) nicht.")
        raise


def _client_id(ctx: Context) -> str:
    try:
        req = ctx.request_context.request
        fwd = req.headers.get("x-forwarded-for", "")
        return fwd.split(",")[0].strip() or (req.client.host if req.client else "unknown")
    except Exception:
        return "unknown"


@mcp.tool()
def list_laws() -> list[str]:
    """Gesetze, zu denen Kommentar vorhanden ist (Kürzel, z.B. 'or')."""
    items = _cached("laws", lambda: gh.list_dir("content/kommentar"))
    return sorted(i["name"] for i in items if i["type"] == "dir")


@mcp.tool()
def list_articles(gesetz: str) -> list[str]:
    """Kommentierte Artikel eines Gesetzes, z.B. ['art-001', 'art-002']."""
    g = _law(gesetz)
    items = _cached(f"arts:{g}", lambda: gh.list_dir(f"content/kommentar/{g}"))
    return sorted(i["name"] for i in items if i["type"] == "dir")


@mcp.tool()
def get_article(gesetz: str, artikel: int) -> str:
    """Kommentar (Markdown mit Frontmatter) zu einem Artikel, z.B. gesetz='or', artikel=1."""
    return _read(f"content/kommentar/{_law(gesetz)}/{_nr(artikel)}/_index.md")


@mcp.tool()
def get_case_law(gesetz: str, artikel: int) -> str:
    """Rechtsprechungsübersicht (Markdown) zu einem Artikel."""
    return _read(f"content/kommentar/{_law(gesetz)}/{_nr(artikel)}/rechtsprechung.md")


@mcp.tool()
def search_commentary(query: str, limit: int = 10) -> list[dict]:
    """Volltextsuche im Kommentar. Liefert Pfade; Inhalt dann mit get_article lesen."""
    q = query.strip()[:200]
    if len(q) < 3:
        raise ValueError("Suchbegriff zu kurz.")
    limit = max(1, min(limit, 20))
    items = _cached(f"s:{q}:{limit}", lambda: gh.search_code(q, limit))
    return [{"path": i["path"], "url": i["html_url"]} for i in items]


@mcp.tool()
def submit_suggestion(
    ctx: Context,
    typ: str,
    beschreibung: str,
    artikel: str = "",
    quellen: str = "",
) -> dict:
    """Anregung oder Korrektur einreichen (anonym). Der Agent prüft sie vor einer Veröffentlichung.

    typ: eine von 'Inhaltliche Korrektur', 'Fehlende Rechtsprechung', 'Neuer Artikel',
    'Gesetzesänderung', 'Sonstiges'. artikel z.B. 'Art. 1 OR'. quellen: BGE-Nummern, Literatur, Links.
    """
    if typ not in SUGGESTION_TYPES:
        raise ValueError(f"typ muss einer von {SUGGESTION_TYPES} sein.")
    beschreibung, artikel, quellen = beschreibung.strip(), artikel.strip(), quellen.strip()
    if len(beschreibung) < 20 or len(beschreibung) > 5000 or len(artikel) > 100 or len(quellen) > 2000:
        raise ValueError("Beschreibung 20–5000 Zeichen, Artikel max. 100, Quellen max. 2000.")

    client = _client_id(ctx)
    now = time.time()
    window = _submissions[client]
    while window and now - window[0] > SUBMIT_WINDOW:
        window.popleft()
    if len(window) >= SUBMIT_LIMIT:
        raise ValueError("Limit erreicht, bitte später erneut versuchen.")
    window.append(now)

    body = (
        f"### Art der Anregung\n\n{typ}\n\n"
        f"### Betroffener Artikel\n\n{artikel or '_No response_'}\n\n"
        f"### Beschreibung\n\n{beschreibung}\n\n"
        f"### Quellen (optional)\n\n{quellen or '_No response_'}\n\n"
        f"---\n_Eingereicht über den Glossagens-MCP-Server._"
    )
    title = f"[Anregung] {artikel or typ}"[:120]
    issue = gh.create_issue(title, body, ["anregung", "pending-review"])
    return {"issue": issue["html_url"], "status": "Eingereicht, wartet auf Prüfung."}


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "streamable-http"))
