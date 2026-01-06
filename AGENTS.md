# Developer Guide

**User docs**: README.md | **Testing**: tests/TESTING.md | **Run**: `python3 app.py` (port 5001)

---

## Quick Reference

| File | Purpose |
|------|---------|
| `app.py` | Flask routes, API endpoints, session management |
| `models.py` | SQLAlchemy models (Person, Feedback, ManagerFeedback) |
| `demo_mode.py` | Demo mode session isolation (per-visitor SQLite databases) |
| `import_orgchart.py` | Excel orgchart import |
| `create_sample_data.py` | Generate fictitious test data (`--demo` for full setup) |
| `create_demo_template.py` | Generate demo template database |
| `conftest.py` | Pytest fixtures |

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
5. **Tenet validation**: 3 strengths, 2-3 improvements (API-enforced)
6. **Workday is source of truth**: Export via copy/paste, import from XLSX only

### Operating Modes
- **Local mode** (default): Persistent SQLite DB, import orgchart CSV, use `/individual`
- **Hosted mode** (`HOSTED_MODE=true`): Ephemeral DB, use `/feedback?for=Name`
- **Demo mode** (route-based): Access via `/demo/*` routes, session-isolated fictitious data

### Naming Conventions
- `user_id` = individual contributor
- `manager_uid` = manager
- `to_user_id` / `from_user_id` = feedback direction

---

## Critical Constraints

### Never Commit
- `feedback.db`, `tenets.json`, `REAL-*.csv` (in .gitignore)
- Any real employee names/feedback in code, comments, or commits

### Never Change Without Full Audit
- Tenet validation (3 strengths, 2-3 improvements) - update all validation points
- Session keys (`user_id`, `manager_uid`) - update all references
- Auto-save debounce timing

### Never Add
- Cloud dependencies or external API calls
- Authentication (intentionally trusted single-user)
- Tenets in database (keep in JSON for version control)

---

## Key Patterns

### Auto-Save
```javascript
let saveTimer = null;
function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveData(), 2000);
}
```

### API Endpoints
```python
@app.route('/api/endpoint', methods=['POST'])
def endpoint():
    data = request.get_json()
    if not data.get('required_field'):
        return jsonify({"success": False, "error": "Missing field"}), 400
    # ... logic ...
    return jsonify({"success": True})
```

### Butterfly Charts
- Individual Chart.js instance per tenet row in CSS Grid
- Strengths (green, right), Improvements (red, left)
- Manager highlights = darker bars, +1 to counts

### PDF Export
- WeasyPrint for HTML-to-PDF, separate `*_pdf.html` templates (no JS)
- Charts via matplotlib as base64 PNG images
- Filename: `{Type}_{Name}_{YYYYMMDD}.pdf`

### Two-Column Tenet Grid
CSS-only fails; requires JS injection in `base.html`:
```javascript
const style = document.createElement('style');
style.textContent = `.tenet-selector { display: grid !important; ... }`;
document.head.appendChild(style);
```

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
| Tenet grid broken | Ensure template extends `base.html` (JS injection required) |

---

## Adding Features

### New API Endpoint
1. Add route to `app.py` with try/except, JSON responses
2. Return `{"success": bool}` or `{"success": false, "error": "msg"}`
3. Add tests to `test_app.py`

### New Database Field
1. Update model in `models.py`
2. Migration: dev = delete DB & reimport; prod = ALTER TABLE
3. Update `import_orgchart.py` if from orgchart
4. Add tests, update UI if user-facing

### New Template
1. Create in `templates/`, extend `base.html` for shared styles
2. Add route in `app.py`
3. Test rendering
