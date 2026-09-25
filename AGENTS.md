# Developer Guide

**User docs**: README.md | **Testing**: tests/TESTING.md | **Run**: `python3 app.py` (port 5001)

---

## Quick Reference

| File | Purpose |
|------|---------|
| `app.py` | Flask routes, API endpoints, session management |
| `models.py` | SQLAlchemy models (Person, Feedback, ManagerFeedback, WorkdayFeedback) |
| `reports.py` | Tenet tallies for charts: manager view, employee view (PDF), team charts |
| `static/style.css` | Shared styles and color variables for every page, loaded by `base.html` |
| `static/workday_format.js` | Copy-for-Workday text (`WorkdayFormat.peer` / `.manager`), loaded by `base.html` |
| `demo_mode.py` | Demo mode session isolation (per-visitor SQLite databases) |
| `scripts/import_orgchart.py` | Orgchart CSV import (CLI) |
| `scripts/import_workday.py` | Workday XLSX import; column mapping from root `workday_config.json` |
| `scripts/create_sample_data.py` | Generate fictitious test data (`--demo` for full setup) |
| `scripts/create_demo_template.py` | Generate demo template database |
| `tests/conftest.py` | Pytest fixtures |
| `Dockerfile` | Container build for OpenShift/Kubernetes |
| `gunicorn.conf.py` | Production WSGI server config (port 8080) |

### Route-to-Template Mapping
| Route | Template |
|-------|----------|
| `/` | `index.html` |
| `/feedback` | `feedback.html` |
| `/individual` | `individual_select.html` |
| `/individual/<user_id>` | `individual_feedback.html` |
| `/manager` | `manager_select.html` |
| `/manager/<manager_uid>` | `manager_dashboard.html` |
| `/manager/report/<user_id>` | `report.html` |
| `/demo` | `demo_index.html` |
| `/demo/*` | Same templates as above (uses demo session DB) |

---

## Core Principles

1. **Privacy-first**: SQLite only, no cloud/telemetry, all data local
2. **Auto-save**: 2-second debounce on all editable fields, no save buttons
3. **Vanilla JS**: No frameworks, use fetch API, Chart.js for charts
4. **No popups**: Use inline indicators ("Saved") never `alert()`
5. **Tenet validation**: 3 strengths, 2-3 improvements, no tenet twice or in both lists;
   same rule for peers and managers (API-enforced)
6. **Workday is source of truth**: Export via copy/paste, import from XLSX only

### Operating Modes
- **Local mode** (default): Persistent SQLite DB, import orgchart CSV, use `/individual`
- **Hosted mode** (`HOSTED_MODE=true`): Ephemeral DB, use `/feedback?for=Name`;
  refuses to start without a `SECRET_KEY` env var (session signing key)
- **Demo mode** (route-based): Access via `/demo/*` routes, session-isolated fictitious data

`@local_only` returns 403 in hosted mode for every non-demo page and `/api/*`
route (JSON body for API routes).

Pages and APIs used by both local and demo mode are defined once, on the `views`
blueprint in `app.py`. It is registered twice: as `local` at `/` and as `demo`
at `/demo`, so each route exists under both prefixes. Inside a `views` route:
- open the DB with `get_db()` (local DB, or the visitor's sandbox under `/demo`);
  it is one session per request, closed at teardown, so never close it yourself
- read/write identity via `flask_session[session_key('user_id')]` (demo keys get
  a `demo_` prefix, so the two modes never share an identity)
- redirect with `url_for('.endpoint')`, which stays in the current mode

The local DB path is `app.config['DATABASE']`; the engine is created once per
process (tests repoint it and call `dispose_db_engine()`). Scripts keep using
`init_db(path)`.

Only routes that exist in one mode go on `app` directly (`/`, `/feedback`,
imports, `/demo`, demo reset). The demo cookie is set by an `after_request`
hook.

Never hard-code a URL path (or host) in templates; `tests/test_pages.py`
rejects `href="/..."`, `fetch('/...')` and the like. In Jinja, link with
`url_for(views ~ '.endpoint')` (`views` is `local` or `demo`, from the context
processor), `url_for(home_endpoint)` for the mode's home page, and plain
`url_for('endpoint')` for app-only routes. In JavaScript, build URLs from
`VIEWS_ROOT` (`''` or `/demo`), call APIs via `API_PREFIX`, and pass app-only
URLs in with `{{ url_for(...) | tojson }}`. The prefix itself is `DEMO_PREFIX`
in `app.py`.

### Naming Conventions
- `user_id` = individual contributor
- `manager_uid` = manager
- `to_user_id` / `from_user_id` = feedback direction

---

## Critical Constraints

### Never Commit
- `feedback.db`, `tenets.json`, `REAL-*.csv`, `instance/` (local session key; all in .gitignore)
- Any real employee names/feedback in code, comments, or commits

### Never Change Without Full Audit
- Tenet validation (3 strengths, 2-3 improvements, no overlap) - update all validation points
  (server: `tenet_selection_error()` in `app.py`, used by the peer and manager
  APIs; pages: `feedback.html`, `individual_feedback.html`, `report.html`)
- Session keys (`user_id`, `manager_uid`) - update all references
- Auto-save debounce timing (`DELAY_MS` in `base.html`)

### Never Add
- Cloud dependencies or external API calls
- Authentication (intentionally trusted single-user)
- Tenets in database (keep in JSON for version control)

---

## Key Patterns

### Auto-Save
Use the shared `window.AutoSave` in `base.html` (2s debounce, keepalive flush on
unload, result shown on the page's `#saveIndicator`):
```javascript
window.AutoSave.debounce(
    `feedback_${selectedColleague}`,   // one pending save per record
    API_PREFIX + '/feedback',
    collectFeedbackData(),             // snapshot now: later edits must not leak in
    rememberSavedFeedback              // optional: runs after the server confirms
);
```
Pass a snapshot (copy arrays), not a getter: a getter read when the timer fires
sends whatever record the page shows by then. Update client-side caches only in
the confirmation callback.

### API Endpoints
```python
@views.route('/api/endpoint', methods=['POST'])  # also served at /demo/api/...
@local_only  # 403 in hosted mode (demo requests pass)
def endpoint():
    data = request.get_json()
    if not data.get('required_field'):
        return jsonify({"success": False, "error": "Missing field"}), 400
    # ... logic ...
    return jsonify({"success": True})
```

### Butterfly Charts
- Counts come from `reports.py` only: `MemberFeedback.manager_view()` (report
  page), `employee_view()` (PDF), `orgchart_team_tally()` / `workday_team_tally()`
  (dashboard). Routes never tally tenets themselves.
- Individual Chart.js instance per tenet row in CSS Grid
- Strengths (green, right), Improvements (red, left)
- Manager highlights = darker bars, +1 to counts

### Copy-for-Workday Format
- Produced only by `static/workday_format.js`; parsed on import by
  `WorkdayFeedback.parse_structured_feedback()` in `models.py`. Never build the
  `[TENETS]` text inline in a template.
- `tests/test_workday_format.py` runs the JS under Node and parses its output,
  so a format change that breaks import fails a test (skipped without Node).

### PDF Export
- The PDF is the **employee's view**; the report page is the manager's view.
  The PDF deliberately excludes Workday feedback (some may not be visible to
  the employee), so its chart counts only in-tool peer feedback plus the
  manager's picks (`MemberFeedback.employee_view()`). Do not "fix" this to
  match the report page.
- WeasyPrint for HTML-to-PDF, separate `*_pdf.html` templates (no JS)
- Charts via matplotlib as base64 PNG images
- Filename: `{Type}_{Name}_{YYYYMMDD}.pdf`

### Page Styles
- Shared styles live in `static/style.css`: color variables (`--accent`,
  `--strength`, `--improvement`, ...) and every component used by more than
  one page (`.context-bar`, `.drop-zone`, `.feedback-checklist`,
  `.copy-section`, `.save-indicator`, messages, the tenet grid). Use the
  variables, not literal colors.
- A page adds only its own CSS, in `{% block extra_styles %}` wrapped in its
  own `<style>` tag; `base.html` renders that block as a sibling of the
  stylesheet link. Never render it inside another `<style>`: a nested tag
  silently drops the page's first rule (`tests/test_pages.py` guards this).
- Text people typed goes alone in a `.user-text` element (keeps line breaks).

---

## Domain Model

### Tenets
- Config: `tenets.json` (not committed), template: `samples/tenets-sample.json`
- Structure: `{version, tenets: [{id, name, category, description, active}]}`

### Feedback Flow
- **Individual (local)**: Import orgchart → select person → choose tenets → add text → auto-saved → copy for Workday
- **Feedback (hosted)**: Access `/feedback?for=Name` → choose tenets → add text → copy for Workday → paste to HR tool
- **Manager**: Import Workday XLSX → view aggregated reports → highlight tenets → copy for Workday / export PDF

### Session
- Flask session stores `user_id` or `manager_uid`
- Direct URL access: `/individual/<id>` and `/manager/<id>` set session
- Switch: `/individual/switch` and `/manager/switch` clear session

---

## Testing

Run: `pytest` | Coverage: `pytest --cov=app --cov=models`

Key fixtures from `conftest.py`:
- `client` - Flask test client
- `db_session` - Database session
- `test_tenets_file` - Temp tenets config

Test naming: `test_[feature]_[scenario]_[expected]`

---

## Common Gotchas

| Issue | Solution |
|-------|----------|
| Database locked | Only one Flask instance; restart app |
| Tenets not loading | Copy `samples/tenets-sample.json` to `tenets.json` |
| Auto-save not working | Check browser console; verify 2s debounce |
| XLSX import error | Must be "Feedback on My Team" Workday export |
| Wrong template edited | Check route-to-template mapping above |
| Tenet grid broken | Ensure template extends `base.html` (loads `static/style.css`) |

---

## Adding Features

### New API Endpoint
1. Add route to `app.py` with try/except, JSON responses (`@views.route` if demo
   mode needs it too)
2. Return `{"success": bool}` or `{"success": false, "error": "msg"}`
3. Add tests to `tests/test_app.py` (hosted/demo behavior: `tests/test_modes.py`)

### New Database Field
1. Update model in `models.py`
2. Migration: dev = delete DB & reimport; prod = ALTER TABLE
3. Update `scripts/import_orgchart.py` if from orgchart
4. Add tests, update UI if user-facing

### New Template
1. Create in `templates/`, extend `base.html` for shared styles
2. Add route in `app.py`
3. Test rendering
