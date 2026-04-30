# Zero Trust Maturity Assessment Dashboard — Local Edition

An AI-assisted Zero Trust maturity assessment platform. Customers complete self-assessments across framework pillars; consultants review responses, generate AI-powered gap findings, map tools to activities, and produce a branded Excel report.

This is the **Local Edition** — runs on any machine with Python 3.11+. No cloud infrastructure required to get started. SharePoint upload is optional.

---

## Quick Start

### macOS / Linux

```bash
git clone https://github.com/gene-png/cyberdashboardV2.git
cd cyberdashboardV2
chmod +x start.sh
./start.sh
```

### Windows

```
git clone https://github.com/gene-png/cyberdashboardV2.git
cd cyberdashboardV2
start.bat
```

The script will:
1. Check Python 3.11+
2. Create a virtual environment and install dependencies
3. Prompt once for an **admin password** and (optionally) an **Anthropic API key**
4. Write a `.env` file with sensible defaults
5. Start the server at **http://localhost:5000**

On every subsequent run it skips setup and goes straight to step 5.

---

## Requirements

| Requirement | Minimum |
|---|---|
| Python | 3.11+ |
| RAM | 512 MB |
| Disk | 500 MB (includes spaCy NLP model) |
| Network | Only needed for AI features |

---

## What Works Without an API Key

| Feature | Without key | With key |
|---|---|---|
| Customer workspace (pillar responses, tool inventory) | ✅ | ✅ |
| Admin review, scoring, finalisation | ✅ | ✅ |
| Excel report export (customer + consultant) | ✅ | ✅ |
| Sensitive terms management | ✅ | ✅ |
| Manual tool-to-activity mapping | ✅ | ✅ |
| Audit log | ✅ | ✅ |
| AI gap findings generation | ❌ | ✅ |
| AI tool mapping suggestions | ❌ | ✅ |
| ATT&CK Coverage Report | ❌ | ✅ |

---

## Configuration

`.env` is created automatically by the start script. To change settings open it in a text editor and restart.

| Variable | Purpose | Required |
|---|---|---|
| `FLASK_SECRET_KEY` | Session signing key | Auto-generated |
| `ADMIN_PASSWORD_HASH` | bcrypt hash of admin password | Set by start script |
| `ANTHROPIC_API_KEY` | Enables AI features | No |
| `ANTHROPIC_MODEL` | Claude model to use | Default: `claude-sonnet-4-6` |
| `DATABASE_URL` | SQLite or Postgres connection string | Default: local SQLite |

### Changing the admin password

```bash
source .venv/bin/activate        # Windows: .venv\Scripts\activate.bat
python scripts/create_admin.py
```

Copy the `ADMIN_PASSWORD_HASH=...` line into `.env` and restart.

### Enabling SharePoint upload

See `docs/guides/Setup and SharePoint Integration Guide.docx`. Then add to `.env`:

```ini
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
SHAREPOINT_SITE_ID=...
SHAREPOINT_DRIVE_ID=...
```

---

## ATT&CK Coverage Report

This feature requires one extra step after first start (downloads ~10 MB from MITRE GitHub):

```bash
source .venv/bin/activate
python scripts/seed_mitre.py
```

Re-run whenever MITRE publishes a new ATT&CK version.

---

## Running on a Different Port

```bash
PORT=8080 ./start.sh          # macOS/Linux
set PORT=8080 && start.bat    # Windows
```

---

## Running Tests

```bash
source .venv/bin/activate
pytest
```

---

## Supported Frameworks

- **DoD Zero Trust Reference Architecture**
- **CISA Zero Trust Maturity Model 2.0**

---

## Documentation

| File | Audience |
|---|---|
| `docs/guides/User Guide.docx` | Customers completing assessments |
| `docs/guides/Admin Guide.docx` | Consultants reviewing and finalising |
| `docs/guides/Setup and SharePoint Integration Guide.docx` | IT / platform operators |

---

## Project Layout

```
app/            Flask application (routes, models, services, templates)
data/           Framework definitions (DoD ZT, CISA ZT)
docs/guides/    User, admin, and setup documentation
scripts/        Utility scripts (admin password, MITRE seed, DB backup)
tests/          pytest test suite (235 tests)
start.sh        Quick start — macOS/Linux
start.bat       Quick start — Windows
requirements.txt
```
