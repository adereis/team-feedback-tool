# Claude Code Instructions - Team Feedback Tool

All development instructions and context for the Team Feedback Tool project.

**For detailed overview, features, and architecture**: See README.md

## Quick Reference

- **Main application**: feedback_app.py (Flask, port 5001)
- **Database models**: feedback_models.py (SQLAlchemy)
- **Templates**: feedback_templates/
- **Quick start guide**: QUICKSTART.md

## Key Development Principles

1. **Privacy-first**: All data stays local, no cloud sync
2. **Auto-save pattern**: 2-second debounce, no manual save buttons
3. **Vanilla JavaScript**: No frameworks, keep it simple
4. **Jinja2 safe filter**: Always use `{{ data | tojson | safe }}` for JSON in JavaScript
5. **Sortable tables**: Use data attributes and JavaScript sorting
6. **No popups**: Use inline messages and indicators only

## Common Patterns

- **Butterfly charts**: Individual Chart.js instances per row in CSS Grid
- **Session management**: Flask session for user/manager identity
- **CSV export**: Browser downloads via `send_file()` and `io.BytesIO`
- **Manager selection**: One-time with session persistence + direct URL support

## Important Notes

- Never commit REAL-*.csv, feedback.db, or tenets.json (see .gitignore)
- Use tenets-sample.json as template for tenets.json
- Port 5001 (different from bonus tool which used 5000)
- Manager feedback highlighting doesn't affect bar lengths (peer counts only)
