# Glossagens — Öffentlicher Juristischer Gesetzeskommentar

## Projektidee

Glossagens ist ein öffentlicher, juristisch fundierter Gesetzeskommentar, der durch einen autonomen Agenten erstellt und gepflegt wird. Jeder kann Artikel bearbeiten (Wiki-Stil), aber Bearbeitungen werden vor Veröffentlichung durch den Agenten verifiziert. Die Öffentlichkeit kann anonym Anregungen und Aufträge einreichen, die der Agent selbständig umsetzt.

## Architektur

### Stack

| Schicht | Technologie |
|---------|-------------|
| Frontend | Hugo + Hextra-Theme → GitHub Pages |
| Content | Markdown-Dateien im GitHub-Repo |
| Deployment | GitHub Actions (auto-deploy bei Push auf `main`) |
| Verifikationspipeline | GitHub Actions Webhook → Hermes Agent |
| Öffentliche Einreichungen | GitHub Issues (strukturiertes Formular) |
| Agent-Hosting | Externer Hetzner-Server mit Nous-Hermes via externer LLM-API |

### Datenfluss

Zwei Eingangskanäle — beide landen in derselben Queue:

```
Kanal A: Anregung (GitHub Issue)          Kanal B: Fertiger Beitrag (Pull Request)
         ↓                                          ↓
Hermes Agent empfängt Webhook             Hermes Agent empfängt Webhook
         ↓                                          ↓
LLM generiert Kommentartext               Strukturprüfung (Page Bundle, Frontmatter)
         ↓                                          ↓
Agent erstellt PR gegen main              LLM-Qualitätsprüfung (Inhalt, Zitate)
         ↓                                          ↓
verify-pr.yml triggert Verifikations-     bei Bestehen: Merge
Webhook                                   bei Ablehnung: PR-Kommentar + Schliessen
         ↓
bei Bestehen: Merge → GitHub Pages Deploy
bei Ablehnung: PR-Kommentar + Schliessen
```

**Kanal A (Issue)**: Für Anregungen — der Agent generiert den Inhalt selbständig.  
**Kanal B (PR)**: Für fertige Beiträge von Menschen oder externen Agenten — der Agent verifiziert nur, generiert nichts.

### Content-Struktur

Artikel werden als **Hugo Page Bundles** angelegt (nicht als Flat-Files):

```
content/
├── kommentar/{gesetz}/
│   ├── _index.md                     ← Gesetzesübersicht
│   └── art-{nr}/                     ← Page Bundle pro Artikel
│       ├── _index.md                 ← Hauptkommentar (Branch Bundle, nicht index.md!)
│       └── rechtsprechung.md         ← Rechtsprechungsübersicht
├── einreichung/_index.md             ← Einreichungsformular
└── ueber/_index.md                   ← Projektbeschreibung

agent/
├── executor.py                       ← Issue- und PR-Verarbeitungslogik
├── webhook_server.py                 ← FastAPI-Endpoints (/webhook, /queue, /approve, /reject)
├── github_client.py                  ← GitHub API-Wrapper
├── mcp_server.py                     ← Öffentlicher MCP-Server (lesen + Anregung einreichen)
├── glossagens-mcp.service            ← systemd-Unit für den MCP-Server
├── requirements.txt
├── .env.example
├── glossagens-agent.service          ← systemd-Unit für Hetzner
└── skills/
    ├── glossagens-content-creation/  ← Skill für Hermes: Artikel erstellen
    │   └── SKILL.md
    └── glossagens-queue/             ← Skill für Hermes: Queue verwalten
        └── SKILL.md

static/
└── agent-skill.md                    ← Öffentlicher Contributor-Skill (für externe Agenten)

.github/
├── workflows/deploy.yml              ← GitHub Pages Deploy
├── workflows/verify-pr.yml           ← Webhook an Hermes bei PR
└── ISSUE_TEMPLATE/anregung.yml       ← Strukturiertes Issue-Formular
```

**Wichtig für den Agenten**: Neue Artikel immer als Page Bundle erstellen:
1. Verzeichnis `content/kommentar/{gesetz}/art-{nr}/` anlegen
2. `_index.md` für den Kommentar (Branch Bundle — nicht `index.md`!)
3. `rechtsprechung.md` für die Rechtsprechungsübersicht

### Frontmatter-Schema — Kommentarartikel (`_index.md`)

```yaml
---
title: "Art. X — Kurztitel"
weight: X
date: YYYY-MM-DD
lastmod: YYYY-MM-DD
description: "..."
tags: ["...", "..."]
agent_verified: true   # nur nach Verifikation durch Hermes
---
```

### Frontmatter-Schema — Rechtsprechungsseite (`rechtsprechung.md`)

```yaml
---
title: "Rechtsprechung zu Art. X Gesetz"
weight: 99
date: YYYY-MM-DD
lastmod: YYYY-MM-DD
description: "Übersicht der Entscheide zu Art. X ..."
tags: ["Rechtsprechung", ...]
agent_verified: false  # wird separat verifiziert
---
```

## PR-Verifikation durch Hermes

Wenn ein externer PR eintrifft, prüft `executor.py` zweistufig:

1. **Strukturprüfung** (automatisch, kein LLM):
   - Kein Flat-File (`art-001.md`) — nur Page Bundle (`art-001/_index.md`)
   - Alle 7 Pflichtfelder im Frontmatter: `title`, `weight`, `date`, `lastmod`, `description`, `tags`, `agent_verified`

2. **Inhaltsprüfung** (LLM):
   - Sachliche Korrektheit, keine erfundenen Zitate
   - Akademischer Zitierstil
   - Kohärenz mit bestehendem Kontext

Bei Strukturfehler: sofortiger Reject ohne LLM-Call.  
Bei Bestehen beider Stufen: automatischer Merge + Deploy.

## GitHub Secrets

- `HERMES_WEBHOOK_URL` — Endpoint auf dem Hetzner-Server
- `HERMES_API_KEY` — Auth-Token für den Webhook

## Offene nächste Schritte

- [ ] Weitere Gesetze/Artikel befüllen
- [ ] Hugo-Build-Check vor Merge in `_execute_pr_merge` einbauen
