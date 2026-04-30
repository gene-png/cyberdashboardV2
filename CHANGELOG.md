# Changelog

All notable changes to the ZT Assessment Dashboard are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.7.0] — 2026-04-29

### Added
- **AI-powered MITRE ATT&CK Coverage Report** (`feat/attack-coverage-report`): Admin can generate a 5-sheet Excel workbook mapping every finalized tool to ATT&CK Enterprise techniques (detect/prevent/respond) with gap classification (Full / Detect Only / Prevent Only / Single Tool / None)
- 3 new models: `MitreTechnique` (ATT&CK technique catalogue), `AttackCoverageRun` (per-tool LLM result cache), `CoverageReport` (generated report metadata + file path)
- 2 new services: `attack_mapper` (LLM prompt construction, JSON parsing, fingerprint cache logic, gap classification) and `attack_coverage_excel` (5-sheet openpyxl workbook builder)
- 3 new admin routes: `GET /admin/assessments/<id>/attack-coverage` (view page), `POST .../generate` (trigger generation), `GET .../download` (file download)
- 5-sheet Excel output: Summary (stats + top 10 gaps), Coverage Matrix (all techniques), Gaps (non-Full entries), Tool Coverage (per-tool stats), Methodology (audit narrative)
- Fingerprint-based caching: SHA-256 hash of tool metadata + activity IDs skips LLM call when nothing has changed since last run
- `scripts/seed_mitre.py`: downloads MITRE ATT&CK Enterprise STIX bundle and upserts `mitre_technique` table; supports `--file` for local JSON and `--dry-run`
- `ATTACK_MODEL` and `REPORTS_DIR` config keys added to `Config` and `TestingConfig`
- ATT&CK Coverage Report link added to Tool Inventory page admin section
- `docs/plans/attack-coverage-report.md` and `docs/decisions/adr-attack-coverage.md`
- 3 new test files (test_attack_mapper, test_attack_coverage_excel, test_attack_coverage_routes) — ~50 new tests

## [0.6.0] — 2026-04-29

### Added
- **AI tool-to-activity mapping** (spec §7.1 / ADR-001): Admin can trigger Claude to suggest which framework activities a tool covers, review suggestions with confidence badges and rationale, and finalize mappings — `ToolActivityMapping`, `MappingSuggestionsLog`, `MappingChange` models; `mapping_suggester` service; `GET/POST /admin/.../mapping`, `.../suggest`, `.../finalize` routes; pillar-grouped checkbox UI
- Tool mapping inventory column: "Mapping" column on inventory page shows "Review Mapping" (pending) or "✓ Mapped (N)" (active) for admin
- **Gap Register**: added Priority (1–4 from severity) and Related Tools (pipe-separated active-mapping tool names) columns
- **Executive Summary Top 5**: always-present "Top 5 Priority Gaps" callout block on Executive Summary sheet (shows "No priority gaps" when none exist)
- **Tool Inventory Mapping sheet**: lists all tools with mapping status and mapped activity names; Redundancy panel (activities with ≥ `REDUNDANCY_THRESHOLD` tools); Underutilization panel (active tools with < `TOOL_MIN_ACTIVITIES` confirmed mappings)
- **Customer sensitive terms**: textarea on workspace overview page lets customers add scrub terms (source=`user_added`) while assessment is editable; `POST /assessments/{id}/terms` route
- **Workspace resume**: workspace route redirects to `assessment.current_step` on load; `?overview=1` bypasses redirect; "Back to Overview" links updated
- **AI generation progress overlay**: JS loading overlay with elapsed-seconds counter on Generate/Regenerate buttons in findings page
- **SharePoint README.txt**: `README.txt` with folder structure guide uploaded alongside other finalization artifacts in `upload_assessment_outputs()`
- `.env.example`: added `REDUNDANCY_THRESHOLD`, `TOOL_MIN_ACTIVITIES`, `MAPPING_MODEL` documentation
- `docs/decisions/adr-tool-mapping-ai.md`: ADR for tool mapping approach selection
- 39 new tests (test_phase6, test_tool_mapping) — 186 total passing

### Changed
- Excel "Tool Inventory" sheet renamed to "Tool Inventory Mapping" (includes redundancy/underutilization analysis)

## [0.5.0] — 2026-04-29

### Added
- spaCy NER scrub (Layer 2b, spec §6.2): ORG/PERSON/GPE entities not in token map are auto-assigned fresh tokens and persisted to `sensitive_term`; graceful-degrade when model unavailable; regex pass now runs before NER to prevent false-positive matches on hex/IP/MAC content
- Customer final report download: `GET /assessments/{id}/report` serves the customer Excel after finalization; "Final Report (Download)" link appears in workspace sidebar on finalized assessments
- Session cookie hardening: `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"` in production config
- HTTPS force-redirect: `before_request` hook redirects `X-Forwarded-Proto: http` → HTTPS (Azure App Service); controlled by `FORCE_HTTPS=true` env var
- Structured logging: `logging.basicConfig` configured in app factory (INFO in production, DEBUG in dev/test)
- `scripts/create_admin.py`: CLI tool that generates a bcrypt hash for `ADMIN_PASSWORD_HASH`
- `.env.example`: documents all required environment variables with descriptions
- `.github/workflows/ci.yml`: runs pytest on every push and PR
- `.github/workflows/deploy.yml`: deploys to Azure App Service on semver tag push
- `requirements.txt`: added `spacy>=3.7,<4.0` and `en_core_web_sm` model wheel
- 17 new tests (test_phase5) — 147 total passing

## [0.4.0] — 2026-04-29

### Added
- CISA ZT framework support: end-to-end verified through all routes (pillar page, HTMX auto-save, Excel export, report generator)
- `_compute_pillar_stats()` now uses framework-agnostic dict keys (`gap_large`, `gap_small`) and generic column headers ("Large Gap", "Small Gap", "Gap %") — works for both DoD ZT and CISA ZT
- Admin audit log view: `GET /admin/assessments/{id}/audit` — shows full audit log table, newest-first, with username resolution
- Sensitive terms management UI: `GET/POST /admin/assessments/{id}/terms` — admin can add user-defined terms (mapped to `[CUSTOM_N]` tokens) and deactivate existing terms; sanitizes HTML input; writes audit log on every change
- Links to Audit Log and Sensitive Terms from admin review page header
- 28 new tests (test_cisa_framework, test_admin_views) — 130 total passing

## [0.3.0] — 2026-04-29

### Added
- HTMX auto-save: per-activity `change` trigger POSTs to `/htmx/assessments/{id}/response/{activity_id}`; returns inline "Saved" indicator with CSS fade-out; no page reload required
- `<noscript>` fallback form on pillar page for no-JS environments
- Rate limiting via Flask-Limiter: 5 POST attempts / 15 min on `/login`; 10 / min on finding regenerate endpoint
- SharePoint service (`sharepoint_service.py`): Graph API client-credentials auth, folder creation, file upload, `upload_assessment_outputs`, `backup_database`
- Finalize route now builds both Excel files and uploads to SharePoint (no-op with warning if credentials not configured)
- Response snapshot JSON and audit CSVs uploaded alongside Excel on finalization
- `scripts/backup_db.py`: nightly DB backup to SharePoint `/Backups/{date}/`, prunes backups older than 30 days
- Admin session countdown timer in navbar (warns at 3 min remaining, shows "expired" at 0)
- `RATELIMIT_ENABLED = False` in TestingConfig to prevent rate-limiter interference with tests
- 25 new tests (test_htmx, test_sharepoint_service) — 102 total passing

## [0.2.0] — 2026-04-29

### Added
- Privacy scrub pipeline (scrub_service.py): Layer 1 token map (org name + variants, usernames, user-defined terms), Layer 2 regex (IPv4, IPv6, MAC, FQDN, email), Layer 3 rehydration with unknown-token warning
- `seed_token_map()`: idempotent seeding of sensitive_term table on assessment creation/generation
- Prompt injection defense in `ai_service.py`: strips instruction-override patterns from evidence notes and tool notes before they enter the AI prompt
- `build_prompt()`: full spec §6.1 prompt structure (framework, pillar, activity, intent, current/target state, evidence, tools, 4-part task)
- `call_anthropic()`: Anthropic API client with model, token counts, and duration logging
- `generate_findings()`: orchestrates all gaps → scrub → AI → store serially; marks no-gap findings stale; logs to ai_call_log and audit_log
- `regenerate_finding()`: per-finding regeneration, updates existing row in place
- Severity formula: gap_size × pillar_weight × 100 → critical/high/medium/low
- Placeholder AI response when ANTHROPIC_API_KEY is not set (enables testing without credentials)
- Admin "AI Findings" page with finding cards, stale indicators, per-finding Regenerate button
- "Generate AI Findings" button in admin review and findings views
- 50 new tests (test_scrub_service, test_ai_service, test_report_generator) — 77 total passing

## [0.1.0] — 2026-04-29

### Added
- Phase 1 skeleton: full Flask application with SQLAlchemy ORM
- Nine database models: Assessment, User, ToolInventory, Response, AdminScore, GapFinding, SensitiveTerm, AuditLog, AICallLog
- Framework JSON fixtures for DoD Zero Trust Reference Architecture (7 pillars, 33 activities) and CISA ZT Maturity Model 2.0 (5 pillars, 17 activities)
- Auth: Flask-Login customer login, logout, admin password gate with 15-minute session timeout
- Dashboard: assessment list view for admin, auto-redirect to workspace for customer users
- New assessment wizard (admin-only): creates assessment + customer credentials
- Assessment workspace: overview with per-pillar progress summary
- Tool inventory: add/delete tools, auto-flip status to in_progress on first edit
- Pillar response forms: current state, target state, evidence notes; saves to DB with audit log entries; marks gap findings stale on edit
- Submit flow: submit assessment → awaiting_review status, locks customer edits
- Admin review: per-pillar admin scoring, gap summary, consultant recommendations
- Admin finalize / reopen flows with audit log entries
- Excel export: customer report (Executive Summary, Gap Register, per-pillar sheets, Tool Inventory, Methodology) and consultant report (all customer sheets + Admin Notes, AI Call Log, Audit Log)
- Privacy scrub service foundation (token-map structure in DB)
- pytest suite: 27 tests covering models, auth, assessment routes, Excel generation
- Smoke test script (scripts/smoke_test.sh): boots server, checks all key routes
- CSRF protection (Flask-WTF) on all forms
- Input sanitization with bleach on all customer free-text fields
