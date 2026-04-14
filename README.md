# C.R.E.E.D. — Compliance, Rights & Ethical Enforcement Directive

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-green.svg)](https://www.python.org/downloads/)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

Open-source, event-driven governance scoring platform for AI systems. Built by [C.R.E.E.D. Institute](https://creed-ai.org) — a Canadian nonprofit advancing enforceable AI ethics.

---

## What It Does

C.R.E.E.D. ingests governance events from AI systems, scores them against configurable compliance frameworks, and produces human-readable grades and embeddable SVG badges.

```
Events → Scoring Engine → Compliance Grade → SVG Badge
```

Feed it what your AI system does. Get back a real-time compliance score.

---

## Features

- **Event Ingestion API** — REST endpoint for logging AI governance events (bias checks, transparency audits, safety validations, and more)
- **Scoring Engine** — Configurable weights per category, rolling window scoring, trend analysis
- **Compliance Grades** — A+ through F letter grades with percentile scoring across categories
- **LCARS Dashboard** — Sci-fi inspired admin UI with live score panels, event history, and badge previews
- **Docker-Ready** — Single `docker compose up` gets you running in under 2 minutes

---

## Quick Start

```bash
git clone https://github.com/KytranKatarn/kytran-creed.git
cd kytran-creed
cp .env.example .env
docker compose up -d
```

Open [http://localhost:8086](http://localhost:8086) to access the dashboard.

---

## API

### Ingest an Event

```bash
curl -X POST http://localhost:8086/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "bias_check",
    "category": "fairness",
    "result": "pass",
    "details": "Demographic parity within 2% threshold"
  }'
```

### Get Scores

```bash
curl http://localhost:8086/scores
```

```json
{
  "overall_grade": "A+",
  "overall_score": 99.7,
  "total_events": 502,
  "categories": {
    "fairness": { "grade": "A+", "score": 99.8 },
    "transparency": { "grade": "A+", "score": 99.9 },
    "safety": { "grade": "A+", "score": 99.5 },
    "accountability": { "grade": "A", "score": 98.2 }
  }
}
```

### Embed a Badge

```html
<img src="https://creed.kytranempowerment.com/badge/overall.svg" alt="C.R.E.E.D. Compliance Score" />
```

Or fetch directly:

```bash
curl http://localhost:8086/badge/overall.svg
```

---

## Architecture

```
kytran_creed/
├── app.py                 # Flask application factory
├── auth.py                # Authentication (local + SSO stub)
├── config.py              # Configuration from environment
├── db.py                  # SQLite database layer
├── models.py              # Data models
├── pg.py                  # PostgreSQL support
├── routes/
│   ├── api_routes.py      # Event ingestion + scores API
│   ├── badge_routes.py    # SVG badge generation
│   └── dashboard_routes.py # LCARS dashboard
├── services/
│   ├── scoring_engine.py  # Compliance scoring logic
│   └── badge_service.py   # SVG badge rendering
├── static/                # CSS + JS
└── templates/             # Jinja2 HTML templates
```

---

## Pricing

| Plan | Price | Features |
|------|-------|----------|
| **Community** | Free | Self-hosted, unlimited events, all API endpoints, SVG badges, LCARS dashboard |
| **Pro** | Coming Soon | Hosted service, multi-system scoring, team access, audit exports, priority support |
| **Enterprise** | Coming Soon | Custom frameworks, SSO, SLA, dedicated compliance analyst, white-label badges |

---

## Testing

```bash
pytest tests/ -v
```

16 tests covering event ingestion, scoring engine, badge generation, and API endpoints.

---

## License

[AGPL-3.0](LICENSE) — Copyright 2026 Kytran Empowerment Inc.

This software is free to use, modify, and distribute under the terms of the GNU Affero General Public License v3.0. If you run a modified version as a network service, you must make your source available.

---

## Links

- **Website**: [creed-ai.org](https://creed-ai.org)
- **Live Demo**: [creed.kytranempowerment.com](https://creed.kytranempowerment.com)
- **Contact**: [contact@creed-ai.org](mailto:contact@creed-ai.org)
- **Parent Org**: [kytranempowerment.com](https://kytranempowerment.com)
