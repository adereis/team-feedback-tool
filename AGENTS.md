# AI Development Credits & Developer Guide

This project was developed with the assistance of AI coding agents to accelerate development and ensure code quality.

**For user-facing documentation**: See README.md

---

## Table of Contents
1. [Quick Reference](#quick-reference)
2. [AI Development History](#ai-development-history)
3. [Coding Standards](#coding-standards)
4. [Architectural Principles](#architectural-principles)
5. [Development Patterns](#development-patterns)
6. [UI/UX Principles](#uiux-principles)
7. [Domain Knowledge](#domain-knowledge)
8. [Development Constraints](#development-constraints)
9. [File Responsibilities](#file-responsibilities)
10. [Testing Guidelines](#testing-guidelines)
11. [Common Gotchas](#common-gotchas)

---

## Quick Reference

- **Main application**: app.py (Flask, port 5001)
- **Database models**: models.py (SQLAlchemy)
- **Templates**: templates/
- **Testing**: Run `pytest` (123 tests) - see TESTING.md

### Key Development Principles

1. **Privacy-first**: All data stays local, no cloud sync
2. **Auto-save pattern**: 2-second debounce, no manual save buttons
3. **Vanilla JavaScript**: No frameworks, keep it simple
4. **Jinja2 safe filter**: Always use `{{ data | tojson | safe }}` for JSON in JavaScript
5. **Sortable tables**: Use data attributes and JavaScript sorting
6. **No popups**: Use inline messages and indicators only
7. **Test coverage**: Write tests alongside features, maintain >80% coverage

### Common Patterns

- **Butterfly charts**: Individual Chart.js instances per row in CSS Grid
- **Session management**: Flask session for user/manager identity
- **Workday XLSX import**: Parse structured feedback with [TENETS] markers
- **Manager selection**: One-time with session persistence + direct URL support
- **Tenet validation**: 3 strengths, 2-3 improvements (enforced by API)
- **JSON serialization**: Use get/set methods in models for tenet lists

### Important Notes

- Never commit REAL-*.csv, feedback.db, or tenets.json (see .gitignore)
- Use samples/tenets-sample.json as template for tenets.json
- Port 5001 (different from bonus tool which used 5000)
- Manager selections count in butterfly chart (+1 per selected tenet)
- External users (not in database) can give feedback via `/individual/<user_id>`

---

## AI Development History

### Development Approach

The Team Feedback Tool was built through an iterative collaboration between human direction and AI implementation:

1. **Requirements Definition**: Human-defined business requirements for peer feedback collection and manager reporting
2. **AI Implementation**: Claude Code (Anthropic) implemented features, wrote tests, and created documentation
3. **Iterative Refinement**: Multiple rounds of feedback to match workflow requirements and UX expectations
4. **Quality Assurance**: Comprehensive test suite (81 tests) ensuring correctness

### AI Contributions

#### Claude Code (Anthropic)
- **Primary Development Agent**: Implemented core application logic, database models, and web interface
- **Testing**: Created comprehensive test suite with 81 tests covering models, routes, and workflows
- **Documentation**: Authored README.md, TESTING.md, and inline code documentation
- **UI/UX**: Designed and implemented all HTML templates with responsive CSS and vanilla JavaScript
- **Sample Data**: Created sample data generators with realistic fictitious employee data

#### Key Features Developed with AI Assistance
- ✅ Flask web application architecture
- ✅ SQLAlchemy ORM models and database schema
- ✅ Individual feedback workflow with tenet selection
- ✅ Manager feedback workflow with Workday XLSX import
- ✅ Auto-save functionality with 2-second debouncing
- ✅ Butterfly charts for feedback visualization (Chart.js)
- ✅ Session-based identity management
- ✅ Workday XLSX import for feedback aggregation
- ✅ Sortable tables with data attributes
- ✅ Manager tenet selection and highlighting
- ✅ Comprehensive pytest test suite

### Human Oversight

All AI-generated code was:
- **Reviewed**: Human verification of correctness and alignment with requirements
- **Tested**: Validated through comprehensive test suite and manual testing
- **Refined**: Iteratively improved based on feedback and edge cases
- **Documented**: Ensured clear documentation for maintainability

### Model Information

- **AI Model**: Claude Sonnet 4.5 (claude-sonnet-4-5@20250929)
- **Platform**: Claude Code CLI (Anthropic)
- **Development Period**: November 2025
- **Total Test Coverage**: 81 tests
- **Lines of Code**: ~2,500 (application + tests)

---

## Coding Standards

### Python Style
- Follow PEP 8 conventions
- Use type hints where appropriate for function parameters and return values
- Maximum line length: 100 characters
- Use descriptive variable names matching existing patterns:
  - `user_id` for individual contributors
  - `manager_uid` for managers
  - `to_user_id` / `from_user_id` for feedback direction
  - `tenet_id` for tenet identifiers

### Database Patterns
- Use SQLAlchemy ORM patterns established in `models.py`
- **JSON serialization**: Tenet lists stored as JSON arrays in TEXT columns
- **Preserve data integrity**: Foreign keys reference Person table
- **Flexible user IDs**: Allow external users not in Person table (for external feedback providers)

### Testing Requirements
- Write tests for all new features before or alongside implementation
- Maintain test coverage above 80%
- Follow existing test patterns in `conftest.py` for fixtures
- Use descriptive test names: `test_[feature]_[scenario]_[expected_result]`
  - Example: `test_save_feedback_validates_strengths_count`
- Each test should be independent and not rely on execution order

### Frontend Patterns
- **Vanilla JavaScript** (no frameworks) - keep it simple
- **2-second debounce** on auto-save operations
- Use fetch API for AJAX calls to backend
- Bootstrap-style CSS classes for consistency
- **Chart.js** for data visualizations
- **Sortable tables**: Use `.sortable` class on headers with `data-sort` attributes
- **Data attributes**: Store sortable values on table rows as `data-{column}` attributes
- **Jinja2 safe filter**: Always use `{{ data | tojson | safe }}` for JSON in JavaScript

### Visualization Patterns
- **Chart.js** for standard charts (bar, line, pie)
- **Butterfly/Diverging Charts**: Individual Chart.js instances per row in CSS Grid
- **PDF Export Charts**: Use matplotlib for server-side chart generation
  - Generate charts as base64-encoded PNG images
  - Embed in HTML templates for PDF conversion
  - Use matplotlib's `Agg` backend (non-interactive)
  - Match visual style with Chart.js web version
- When creating complex charts:
  - Start with simplest approach first
  - Break down into smaller independent components
  - Use CSS Grid for precise alignment
  - Prioritize visual clarity over complex single-chart solutions

### PDF Export Pattern
- **WeasyPrint** for HTML-to-PDF conversion
- Create separate `*_pdf.html` templates (no JavaScript)
- Generate charts server-side using matplotlib as base64 images
- Use `data:image/png;base64,{{image}}` for embedding
- Return PDF via `send_file()` with `mimetype='application/pdf'`
- Filename format: `{ReportType}_{Name}_{YYYYMMDD}.pdf`

---

## Architectural Principles

### Data Flow
- **Orgchart is source of truth** for employee data (names, job titles, org structure)
- **Feedback is persistent** and stored in SQLite database
- **Tenets are configurable** via tenets.json (organization-specific)
- Import flow: Orgchart CSV → Web UI or `import_orgchart.py` → SQLite → Flask API → Web UI
- Export flow: Web UI → Flask API → CSV → Manager import

### Key Design Decisions

#### Local-First Architecture
- **No cloud dependencies**: SQLite only, no external databases
- **No authentication**: Designed for trusted environment (internal tool)
- **Privacy-focused**: All sensitive data stays on user's machine
- No telemetry or external API calls

#### Auto-Save Pattern
- 2-second debounce on feedback changes (defined in individual_feedback.html)
- Prevents excessive API calls during typing
- Visual feedback on save status ("✓ Saved" indicator)
- Preserves user work without explicit "Save" button

#### Tenet Selection Model
- **Individuals select**: 3 strengths, 2-3 improvements per feedback
- **Managers highlight**: Any number of tenets from aggregated feedback
- **Validation**: API enforces selection counts for individuals
- **Aggregation**: Counts combine peer + manager selections (manager counts as +1)

#### Session-Based Identity
- **Flask session** stores current user_id (individual) or manager_uid (manager)
- **Persistent identity**: Session maintained across page loads
- **Direct URL access**: `/individual/<user_id>` and `/manager/<manager_uid>` for bookmarking
- **Switch users**: `/individual/switch` and `/manager/switch` clear session

#### Butterfly Chart Design
- **Strengths (right, green)**: Positive feedback counts
- **Improvements (left, red)**: Areas for growth counts
- **Net sorting**: Sorted by (strengths - improvements) descending
- **Manager highlights**: Selected tenets shown with darker/highlighted bars
- **Per-row charts**: Individual Chart.js instance per tenet for precise alignment

### Don't Break These
- **Never commit** `feedback.db`, `tenets.json`, or `REAL-*.csv` files (privacy - already in .gitignore)
- **Never change tenet validation** (3 strengths, 2-3 improvements) without updating all UIs
- **Never break the 2-second auto-save debounce** pattern
- **Never add cloud dependencies** or external API calls
- **Never store tenets configuration** in database (keep in JSON file for version control)

---

## Development Patterns

### Adding a New API Endpoint

1. Add route to `app.py`
2. Follow existing pattern: try/except with JSON error responses
3. Use appropriate HTTP methods (GET for reads, POST for writes, DELETE for removals)
4. Return JSON with consistent structure: `{"success": bool}` or `{"success": false, "error": "message"}`
5. Add corresponding tests to `test_app.py`
6. Update API documentation in code comments

Example pattern:
```python
@app.route('/api/new_endpoint', methods=['POST'])
def new_endpoint():
    data = request.get_json()

    # Validation
    if not data.get('required_field'):
        return jsonify({"success": False, "error": "Missing required_field"}), 400

    # Business logic
    session = init_db()
    result = perform_operation(data)
    session.commit()
    session.close()

    return jsonify({"success": True})
```

### Adding a Database Field

1. Update model in `models.py` (Person, Feedback, or ManagerFeedback)
2. Handle migration (we don't use Alembic - manual ALTER TABLE or recreate database)
3. Update `import_orgchart.py` if field comes from orgchart export
4. Add tests for new field in `test_models.py`
5. Update UI templates if field is user-facing
6. Update sample data generator if needed

**Migration approach**: This project uses simple SQLite, so:
- For dev: Delete `feedback.db` and re-import orgchart
- For production: Write manual ALTER TABLE statement or provide migration script

### Adding a New Template/Page

1. Create HTML template in `templates/` directory
2. Extend appropriate base (or create standalone)
3. Add route in `app.py` to render template
4. Add navigation link if needed
5. Test rendering with `test_app.py`

### Inline Editing with Auto-Save Pattern

For editable fields with auto-save:

1. **HTML Structure**:
   ```html
   <input type="text"
          id="field_name"
          value="{{ value }}"
          onblur="scheduleSave()"
          oninput="scheduleSave()">
   ```

2. **JavaScript Auto-Save**:
   ```javascript
   let saveTimer = null;

   function scheduleSave() {
       if (saveTimer) clearTimeout(saveTimer);
       saveTimer = setTimeout(() => {
           saveData();
       }, 2000);
   }

   function saveData() {
       fetch('/api/endpoint', {
           method: 'POST',
           headers: {'Content-Type': 'application/json'},
           body: JSON.stringify(data)
       })
       .then(r => r.json())
       .then(data => {
           if (data.success) showSaveIndicator();
       });
   }
   ```

3. **Visual Feedback**:
   - Show temporary "✓ Saved" indicator for 2 seconds
   - Use inline messages, never popups/alerts

### UI Design Iteration

When adding new features, follow this pattern:
1. **Implement** with initial UI (may be verbose)
2. **Gather user feedback** about UI space and usability
3. **Simplify** based on feedback
4. **Document** the final pattern for consistency

**Principle**: Minimize UI clutter. Prefer inline editing over separate forms/panels.

---

## UI/UX Principles

### Hide Implementation Details
- Don't expose internal technical details unless they help users make decisions
- Show: Feedback counts, tenet names, aggregated results
- Hide: Database IDs, JSON structures, internal calculation details

### Prefer Inline Editing
- Make fields editable where appropriate
- Provide visual feedback on hover/focus
- Consistent auto-save pattern (2-second debounce)
- No separate "Edit" mode - everything editable in place

### No Popups or Alerts
- Use inline messages and indicators only
- Examples: "✓ Saved", "Deleting...", "Exported"
- Never use JavaScript `alert()` or `confirm()`
- Exception: Critical errors that prevent operation

### Sortable Tables by Default
- Users expect to click column headers to sort
- Store sortable values in `data-{column}` attributes on rows
- Add `.sortable` class to clickable headers
- Default to most relevant sort (e.g., highest feedback count descending)

---

## Domain Knowledge

### Feedback Collection Philosophy

- **Tenet-based feedback**: Feedback organized around organizational cultural tenets
- **3 strengths required**: Forces prioritization of top strengths
- **2-3 improvements allowed**: Flexibility for focused or broader feedback
- **Text explanations**: Both tenet selections and free-text feedback
- **Anonymous aggregation**: Individual feedback aggregated for manager view

### Tenet Configuration

- **Stored in**: `tenets.json` (org-specific, not committed)
- **Template**: `samples/tenets-sample.json` (version controlled)
- **Structure**:
  ```json
  {
    "version": "2025-Q4",
    "tenets": [
      {
        "id": "unique_id",
        "name": "Display Name",
        "category": "Category",
        "description": "Explanation",
        "active": true
      }
    ]
  }
  ```
- **Active flag**: Inactive tenets don't appear in UI
- **Versioning**: Track tenet changes over time with version field

### Orgchart Import

- **Source**: Excel export from HR system
- **Required columns**:
  - User ID (unique identifier)
  - Name
  - Job Title
  - Email
  - Manager UID (can be null for top-level)
- **Import preserves**: Existing feedback data (never overwrites)
- **Import updates**: Person records (names, titles, org structure)

### Workflow Modes

#### Individual Mode
1. Select or enter user ID
2. View list of people organized by manager
3. Give feedback: select tenets + write text
4. Auto-saved as you work

#### Manager Mode
1. Select manager identity
2. Import Workday XLSX export ("Feedback on My Team")
3. View team member list with feedback counts
4. View aggregated reports per team member
5. Highlight key tenets and add manager feedback
6. Export PDF reports

### Manager Feedback Integration

- **Manager selections count**: Each selected tenet adds +1 to count (same as peer feedback)
- **Shown in butterfly chart**: Manager highlights displayed with darker bars
- **Text feedback**: Separate field for manager's summary/commentary
- **Auto-saved**: Manager inputs auto-save with 2-second debounce

### Workday XLSX Import

- **Source**: "Feedback on My Team" export from Workday
- **Import to manager**: Upload XLSX to aggregate feedback
- **Structured feedback**: Parsed from [TENETS] markers embedded in feedback text
- **Generic feedback**: Free-text feedback without tenet selections
- **Duplicate handling**: Skip existing feedback on re-import based on content hash
- **Column detection**: Configurable via `workday_config.json`

---

## Development Constraints

### Do NOT

#### Architecture & Dependencies
- ❌ Add cloud dependencies or external API calls
- ❌ Add authentication/authorization (intentionally single-user/trusted)
- ❌ Store tenets configuration in database (keep in JSON for version control)
- ❌ Use absolute file paths (support running from any directory)

#### Data & Privacy
- ❌ Commit `feedback.db`, `tenets.json`, or any real employee data
- ❌ Commit files matching `REAL-*.csv` pattern
- ❌ Log sensitive employee information (names, feedback text)
- ❌ Add telemetry or analytics that phone home

**CRITICAL: Privacy and Data Protection**

This project handles **real employee feedback data** which is highly sensitive and confidential.

**Safe vs. Private Data:**

SAFE - Auto-generated fictitious data:
- Files generated by `create_sample_data.py`
- Sample tenets: `samples/tenets-sample.json`
- Test fixtures in `conftest.py`
- Data in test files using sample fixtures
- ✅ Safe to use in examples, documentation, tests, and git commits

PRIVATE - Real orgchart exports and feedback:
- `feedback.db` - database with real feedback (already in .gitignore)
- `tenets.json` - organization-specific tenets (in .gitignore)
- `REAL-*.csv` - any file prefixed with REAL- (in .gitignore)
- Any orgchart export containing real employee names
- Any feedback CSV with actual employee feedback
- ❌ NEVER commit, reference, or include examples from these files

**Strict Rules for Private Data:**

1. NEVER commit private data files
   - Check .gitignore before any git operations
   - Real data files must remain untracked

2. NEVER use real data in examples
   - Documentation must use fictitious sample data only
   - Code examples should reference sample data generators
   - Test cases must use fixtures with made-up data

3. NEVER put real data in git history
   - No real employee names in commit messages
   - No actual feedback text in code comments
   - No real data in analysis documents that get committed

4. Analysis files with real data must stay local
   - Analysis documents examining real exports: untracked
   - Only commit sanitized versions with fictitious examples

**Safe Workflow:**

When asked to analyze real data:
1. ✅ Read and analyze the file locally
2. ✅ Create analysis documents in local directory
3. ✅ Use generic/sanitized examples if needed
4. ❌ Do NOT stage or commit files with real data
5. ❌ Do NOT put real examples in committed documentation
6. ✅ Verify git status before committing anything

**When in doubt**: Keep it local, don't commit it. Real employee data must NEVER leave the local machine or enter version control.

#### Code Changes
- ❌ Change tenet selection validation (3 strengths, 2-3 improvements) without updating all validation points
- ❌ Break the 2-second auto-save debounce pattern
- ❌ Change Flask session keys (`user_id`, `manager_uid`) without updating all references

---

## File Responsibilities

### Core Application

#### `app.py` (Main Flask Application)
- Flask routes and API endpoints
- Request handling and validation
- JSON response formatting
- Session management
- CSV export generation
- **Do not add**: Database models (belongs in models.py)

#### `models.py` (Database Schema)
- SQLAlchemy ORM models (Person, Feedback, ManagerFeedback)
- Database schema definitions
- Model methods for data conversion (`to_dict()`)
- JSON serialization helpers (get/set methods for tenet lists)
- **Do not add**: Business logic or route handlers (belongs in app.py)

#### `import_orgchart.py` (Orgchart Import)
- Excel file reading with openpyxl
- Orgchart column mapping
- Data transformation and cleaning
- Database population with employee data
- **Preserves**: Existing feedback data (never deletes or overwrites feedback)

### Data Generation & Sample Data

#### `create_sample_data.py` (Sample Data Generator)
- Generates fictitious employee data with tech-themed pun names
- Creates sample orgchart CSV and optionally populates database
- Two modes: small team (12 employees) or large org (50 employees, 5 managers)
- `--demo` flag provides complete setup: orgchart, peer feedback, manager feedback, export CSVs

**Usage:**
```bash
python3 create_sample_data.py              # Orgchart CSV only
python3 create_sample_data.py --large      # Large org CSV only
python3 create_sample_data.py --demo       # Full demo setup (recommended)
python3 create_sample_data.py --large --demo  # Large org full demo
```

**Demo mode creates:**
- `sample-orgchart.csv` - Orgchart for import
- `feedback.db` - Populated with Person, Feedback, and ManagerFeedback records
- `sample-workday-feedback.xlsx` - Workday XLSX for testing import workflow

### Testing

#### `conftest.py` (Test Fixtures)
- Shared pytest fixtures
- Test database setup with temporary SQLite
- Sample data fixtures (people, feedback, tenets)
- Flask app and client fixtures
- **Use these fixtures** in all new tests

#### Test Files
- `test_models.py` - Model tests (28 tests)
- `test_app.py` - Route and API tests (43 tests)
- `test_integration.py` - Integration tests (15 tests)
- Follow naming convention for pytest discovery

See `TESTING.md` for comprehensive testing documentation.

### Templates (HTML/UI)

**Route-to-Template Mapping** (verify you're editing the right file!):
| Route | Template |
|-------|----------|
| `/` | `index.html` |
| `/feedback` | `feedback.html` |
| `/individual` | `individual_select.html` |
| `/individual/<user_id>` | `individual_feedback.html` |
| `/manager` | `manager_select.html` |
| `/manager/<manager_uid>` | `manager_dashboard.html` |
| `/manager/report/<user_id>` | `report.html` |

#### `templates/base.html` (Base Template)
- Shared styles and scripts inherited by all templates
- **Contains shared tenet selector CSS and JS** - edit here for grid layout changes
- Footer navigation links
- Two-column grid CSS injection (workaround for specificity issues)

#### `templates/index.html` (Home Page)
- Mode selection (individual vs manager)
- Landing page navigation

#### `templates/feedback.html` (Workday Feedback Flow)
- Streamlined feedback form for external providers
- Used when accessing `/feedback?for=Name`
- Copy-to-clipboard for pasting into Workday
- No orgchart/database dependency

#### `templates/individual_select.html` (Individual Login)
- User selection/input interface
- List of people from database
- Custom user ID input for external users

#### `templates/individual_feedback.html` (Feedback Collection)
- People selector (organized by manager)
- Tenet selection interface
- Text feedback fields
- Existing feedback list (editable/deletable)
- Auto-save functionality (2-second debounce)

#### `templates/export_list.html` (Export Manager List)
- List of managers with feedback counts
- Download links per manager
- Shows associates with pending feedback

#### `templates/manager_select.html` (Manager Login)
- Manager selection interface
- List of managers (people with direct reports)

#### `templates/manager_dashboard.html` (Manager Dashboard)
- Team member list
- Feedback counts per person
- Workday XLSX import interface (drag & drop)
- Navigation to individual reports
- Team-wide butterfly chart

#### `templates/report.html` (Feedback Report)
- Butterfly chart visualization (Chart.js)
- Aggregated tenet counts
- Individual feedback items
- Manager tenet selection interface
- Manager text feedback field
- Auto-save functionality
- PDF export button

#### `templates/report_pdf.html` (PDF Report Template)
- Simplified HTML template for PDF generation (no JavaScript)
- Team member info and feedback summary
- Butterfly chart as embedded base64 PNG image
- Peer feedback comments (anonymous)
- Manager feedback (attributed)
- Print-optimized styling for WeasyPrint

### Configuration Files

#### `samples/tenets-sample.json` (Template)
- Version controlled sample tenets
- Template for creating organization-specific `tenets.json`
- Documents expected structure and fields

#### `tenets.json` (Organization-Specific)
- **Not committed** (in .gitignore)
- Organization's actual tenets configuration
- Created by copying and modifying samples/tenets-sample.json

### Generated/Temporary Files (Never Commit)

These files are in `.gitignore` and should **never** be committed:
- `feedback.db` - Active database with employee and feedback data
- `tenets.json` - Organization-specific tenets configuration
- `REAL-*.csv` - Any CSV files prefixed with REAL-
- `__pycache__/` - Python bytecode
- `.pytest_cache/` - Pytest cache
- `htmlcov/` - Coverage reports
- `*.db-test` - Test database files

---

## Testing Guidelines

### Running Tests

```bash
# All tests
pytest

# Specific module
pytest test_models.py
pytest test_app.py
pytest test_integration.py

# With verbose output
pytest -v

# Specific test
pytest test_app.py::TestFeedbackAPI::test_save_feedback_new_creates_record

# With coverage
pytest --cov=app --cov=models --cov-report=html
```

### Writing New Tests

1. Use fixtures from `conftest.py`:
   - `test_db` - Temporary database path
   - `db_session` - Database session
   - `app` - Flask app configured for testing
   - `client` - Flask test client
   - `test_tenets_file` - Temporary tenets configuration
   - `sample_csv_feedback` - Sample CSV data

2. Follow naming convention:
   - Test files: `test_*.py`
   - Test classes: `Test*`
   - Test methods: `test_*`

3. Test structure (Arrange-Act-Assert):
   ```python
   def test_feature_scenario_expected_result(client, db_session):
       # Arrange
       with client.session_transaction() as sess:
           sess['user_id'] = 'test_user'
       data = {"field": "value"}

       # Act
       response = client.post('/api/endpoint',
                            data=json.dumps(data),
                            content_type='application/json')

       # Assert
       assert response.status_code == 200
       assert json.loads(response.data)['success'] is True
   ```

4. Test isolation:
   - Each test gets a fresh database
   - Don't rely on execution order
   - Use `db_session.expire_all()` to refresh database state

See `TESTING.md` for comprehensive testing documentation.

---

## Common Gotchas

### Issue: Database Locked
**Cause**: Multiple processes accessing SQLite database
**Solution**: Ensure only one Flask instance running, restart app

### Issue: Auto-Save Not Working
**Cause**: JavaScript error or debounce timing
**Check**: Browser console for errors, verify 2-second delay
**Solution**: Check network tab for API calls, ensure endpoint responding

### Issue: Tenets Not Loading
**Cause**: Missing or invalid `tenets.json` file
**Solution**: Copy `samples/tenets-sample.json` to `tenets.json` and customize

### Issue: External User Can't Give Feedback
**Cause**: Code expects user in Person table
**Should Work**: System allows any user_id via `/individual/<user_id>`
**Debug**: Check session setting and API endpoints allow arbitrary user_ids

### Issue: Manager Selections Not Showing in Chart
**Cause**: Manager selections not counted in aggregation
**Should Work**: Manager selections add +1 to counts (see app.py:500-506)
**Debug**: Verify ManagerFeedback record exists and get_selected_* methods work

### Issue: Workday XLSX Import Creates Duplicates
**Cause**: Import logic not checking for existing feedback
**Should Never Happen**: Import skips duplicates based on content hash
**Debug**: Check database for duplicate entries, verify hash calculation

### Issue: Workday XLSX Import Shows Error
**Cause**: Wrong file format or missing required columns
**Expected**: XLSX file with columns: About, From, Feedback, etc.
**Solution**: Use the "Feedback on My Team" export from Workday

### Issue: Two-Column Tenet Grid Not Working
**Cause**: CSS-only approaches fail due to specificity issues
**Solution**: JavaScript CSS injection is REQUIRED (not just CSS)
**Location**: `base.html` contains the shared JS injection that forces the grid
**Pattern**: The workaround injects `!important` styles via JavaScript:
```javascript
const style = document.createElement('style');
style.textContent = `.tenet-selector { display: grid !important; ... }`;
document.head.appendChild(style);
```
**Warning**: If adding tenet selectors to a new template, ensure it extends `base.html`

### Issue: Editing Wrong Template
**Cause**: Multiple templates handle similar functionality
**Prevention**: Check the route-to-template mapping in File Responsibilities section
**Example**: `/feedback` uses `feedback.html`, NOT `individual_feedback.html`

---

## Development Best Practices

### Complex Visualizations
**Lesson**: When Chart.js doesn't naturally support your visualization (e.g., butterfly charts):
1. Try the native Chart.js approach first
2. If alignment issues occur, break into independent components
3. Use individual charts per row with CSS Grid for precise layout
4. Simpler is better - don't force a library to do what it wasn't designed for

**Implementation** (report.html):
- One Chart.js horizontal bar chart per tenet row
- CSS Grid for alignment: `display: grid; grid-template-columns: 1fr 1fr;`
- Separate datasets for strengths (green, right) and improvements (red, left)
- Manager selections highlighted with darker colors

### Feature Rollout
**Pattern**: When adding major features:
1. Start with data model (add database fields)
2. Update import/export logic
3. Create UI for data entry/display
4. Add analytics/reporting
5. Update sample data generators
6. Write comprehensive tests (data model → import → display → analytics)
7. Document patterns in CLAUDE.md

### Test-Driven Development
**Approach**: Write tests alongside or before implementation:
1. Create fixtures for test data
2. Write tests for expected behavior
3. Implement feature to pass tests
4. Verify all tests pass
5. Document testing patterns

**Result**: 123 tests covering all major functionality ensures confidence in changes.

### Session Management
**Pattern**: Flask session for identity without full auth:
1. Store minimal state: `user_id` or `manager_uid`
2. Allow direct URL access: `/individual/<user_id>` sets session
3. Provide switch endpoints: `/individual/switch` clears session
4. Test session persistence across requests
5. Support external users not in database

### Template Style Centralization
**Lesson**: When the same CSS/JS appears in multiple templates, centralize it in `base.html`:
1. Identify duplicate styles across templates (e.g., `.tenet-selector`, `.tenet-item`)
2. Move shared styles to `base.html` in the main `<style>` block
3. Move shared JS workarounds to `base.html` in a `<script>` before `{% block scripts %}`
4. Remove duplicates from individual templates
5. Test all affected pages to ensure styles still apply

**Current shared styles in base.html**:
- Tenet selector grid layout (CSS + JS injection workaround)
- Tenet item states (hover, selected-strength, selected-improvement, disabled)
- Common UI classes (.btn, .card, .form-group, etc.)

### Auto-Save Implementation
**Pattern**: Consistent auto-save across all editable fields:
1. 2-second debounce on input/change events
2. Clear timer on new input
3. Save via fetch() POST to API
4. Show temporary "✓ Saved" indicator
5. Handle errors gracefully (log, don't alert)

### Iterative UI Refinement
**Approach**: When refining UX:
1. Start with functional but potentially verbose UI
2. Get user feedback on real estate usage
3. Streamline and simplify
4. Make tables sortable by default
5. Use inline editing where possible
6. Remove unnecessary panels/sections

---

## Related Projects

This project shares patterns and audience with **performance-rating-and-bonus** (same author).

### Shared Patterns
Both projects follow these conventions for consistency:
- **Project structure**: `app.py`, `models.py`, `templates/`, `scripts/`, `samples/`, `docs/`
- **Documentation**: `AGENTS.md` as primary developer guide, `CLAUDE.md` as redirect
- **Tenets system**: Same JSON structure in `samples/tenets-sample.json`
- **Workday integration**: Local companion tools, not replacements
- **Auto-save**: 2-second debounce on all editable fields
- **Privacy-first**: SQLite, no cloud, no telemetry

### Cross-Pollination Opportunities

#### From performance-rating-and-bonus:
- **Historical data preservation**: Period archiving with snapshots for quarter-over-quarter comparison
- **ID-based identification**: All employee lookups use unique IDs, not names (prevents duplicate name issues)
- **Period comparison analytics**: View trends across rating periods
- **Employee trend visualization**: Performance history with improving/stable/declining indicators

#### To performance-rating-and-bonus:
- **PDF export pattern**: WeasyPrint + matplotlib for server-side report generation (see `app.py` and `templates/report_pdf.html`)
- **Workday XLSX import**: Flexible column detection with header-based mapping (see `scripts/import_workday.py`)
- **Two-column tenet layouts**: CSS Grid with JavaScript fallback for compact selection UI

### Ports
- **performance-rating-and-bonus**: Port 5000
- **team-feedback-tool**: Port 5001 (can run simultaneously)

---

## Future Enhancements

Potential areas for expansion (not yet implemented):

- [x] PDF export for manager reports (✅ Implemented)
- [ ] Email feedback reminders
- [ ] Historical feedback comparison (quarter-over-quarter) - see performance-rating-and-bonus for reference
- [ ] Multi-manager organizations (skip levels)
- [ ] Anonymous feedback option
- [ ] Feedback templates/prompts
- [ ] Bulk feedback operations
- [ ] Read-only sharing mode for calibration sessions
- [ ] Database migration system (Alembic)
- [ ] API documentation (Swagger/OpenAPI)

---

*This file serves dual purposes:*
1. *Claude Code session instructions and context*
2. *Developer guide for AI agents and humans working on this codebase*

*Following best practices for AI-assisted software development.*
