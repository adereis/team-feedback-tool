# Team Feedback Tool

A privacy-focused local web application for collecting and aggregating peer feedback based on team tenets. Integrates with Workday for feedback requests and collection.

## Overview

This tool enables teams to:
- **Individuals**: Provide structured feedback to colleagues using team tenets
- **Managers**: Aggregate feedback from Workday, add insights, and generate reports

All data stays local—no cloud sync, no external dependencies.

Example Report:

![Feedback Report Example](feedback-report-example.png)

## Workday Integration Workflow

The tool integrates with Workday (or similar HR systems) for feedback collection:

1. **Request**: Manager or employee requests feedback via Workday, including a link to this tool
2. **Notify**: Feedback providers receive notification with tool link
3. **Provide**: Providers clone the repo, run locally, select tenets and provide feedback
4. **Copy**: Click "Copy for Workday" to get formatted text, paste into Workday
5. **Import**: Manager downloads "Feedback on My Team" XLSX from Workday, imports into tool
6. **Report**: Tool aggregates feedback for butterfly charts and reports

### Two Types of Feedback

| Type | Source | In Butterfly Chart |
|------|--------|-------------------|
| **Structured** | Tool-assisted (contains `[TENETS]` marker) | Yes |
| **Generic** | Other Workday workflows (free-text) | No (shown separately) |

## Features

### For Feedback Providers
- Select 3 tenet strengths and 2-3 areas for improvement
- Two-column compact tenet layout for faster selection
- Auto-save with 2-second debounce (no manual save needed)
- Visual progress checklist (yellow → green when complete)
- **Copy for Workday** button generates formatted text with tenets
- Preview of formatted output before copying
- Support for external feedback providers (not in orgchart)

### For Managers
- **Import Workday XLSX**: Drag & drop "Feedback on My Team" export
- Automatic detection of structured vs generic feedback
- Date range filtering (default: last 3 months, or custom range)
- Sortable team table (name, job title, feedback count)
- Butterfly chart visualization of aggregated peer feedback
- Separate "Additional Feedback" section for generic entries
- Highlight specific tenets for emphasis in reports
- Add manager's own feedback and comments
- Export PDF reports
- Legacy CSV import still supported

## Quick Start

### 1. Generate Sample Data

Try the tool with fictitious data:

```bash
# Full demo setup: orgchart, peer feedback, manager feedback, export CSVs
python3 create_sample_data.py --demo

# Or for a larger organization (50 employees, 5 managers)
python3 create_sample_data.py --large --demo

# Start the app
python3 feedback_app.py
```

Access at: http://localhost:5001

Sample managers include: Della Gate (dgate), Rhoda Map (rmap), Kay P. Eye (keye), Agie Enda (aenda), Mai Stone (mstone)

### 2. Use with Real Data

```bash
# Start the application
python3 feedback_app.py
```

**Import your orgchart via Web UI** (Recommended):
1. Go to http://localhost:5001
2. Drag & drop your orgchart CSV onto the upload zone (or click to browse)

**Or via Command Line**:
```bash
python3 import_orgchart.py REAL-orgchart-export.csv
```

## Workflow

### Workday-Integrated Workflow (Recommended)

1. **Request Feedback**: Manager or employee requests feedback via Workday, including link to this tool in the request message
2. **Providers Give Feedback**:
   - Clone this repo and run locally: `python3 feedback_app.py`
   - Go to http://localhost:5001/individual
   - Select tenets and write feedback for the colleague
   - Click "Copy for Workday" and paste the formatted text into Workday
3. **Manager Aggregates**:
   - Download "Feedback on My Team" XLSX from Workday
   - Import XLSX at http://localhost:5001/manager
   - Tool parses structured feedback (with tenets) and generic feedback separately
   - Review reports, add highlights, export PDFs

### Legacy Workflow (CSV-based)

1. **Setup**: Import your orgchart CSV (drag & drop on home page)
2. **Individuals**: Give feedback for colleagues, export CSVs grouped by manager
3. **Managers**: Import feedback CSVs, review reports, export PDFs

## Requirements

```bash
pip install flask sqlalchemy
```

Or install from requirements.txt:
```bash
pip install -r requirements.txt
```

## CSV Formats

### Orgchart Import Format

```csv
Name,User ID,Job Title,Location,Email,Manager UID
Paige Duty,pduty,Staff SRE,Boston MA,pduty@example.com,dgate
Della Gate,dgate,Engineering Manager,Raleigh NC,dgate@example.com,
```

### Feedback Export Format

```csv
From User ID,To User ID,Strengths (Tenet IDs),Improvements (Tenet IDs),Strengths Text,Improvements Text
pduty,llatency,"ownership,quality,collaboration","communication,innovation","Lee excels...","I see opportunities..."
```

## Tenets Configuration

The application looks for tenets in this order:
1. `tenets.json` (your organization's customized tenets)
2. `tenets-sample.json` (fallback with tech-themed examples)

To customize tenets for your organization:

```bash
# Copy the sample file
cp tenets-sample.json tenets.json

# Edit tenets.json with your organization's values
# (This file is in .gitignore, so it stays private)
```

Tenet format:

```json
{
  "tenets": [
    {
      "id": "ownership",
      "name": "Ownership & Accountability",
      "description": "Takes responsibility for outcomes",
      "active": true
    }
  ]
}
```

Set `"active": false` to temporarily disable a tenet without deleting it.

## Architecture

- **Flask**: Web framework (port 5001)
- **SQLAlchemy**: ORM for database operations
- **SQLite**: Local database (feedback.db)
- **Jinja2**: Template engine
- **Chart.js**: Butterfly chart visualizations
- **Vanilla JavaScript**: No frameworks, simple and maintainable

### Database Schema

**persons**: Imported from orgchart
- user_id (PK), name, job_title, location, email, manager_uid (FK)

**feedback**: Peer feedback entries (legacy CSV workflow)
- id (PK), from_user_id (FK), to_user_id (FK)
- strengths (JSON array of tenet IDs)
- improvements (JSON array of tenet IDs)
- strengths_text, improvements_text

**workday_feedback**: Feedback imported from Workday XLSX
- id (PK), about (recipient name), from_name (provider name)
- question, feedback (raw text), asked_by, request_type, date
- is_structured (1 if contains [TENETS] marker)
- strengths, improvements (JSON arrays, if structured)
- strengths_text, improvements_text (if structured)

**manager_feedback**: Manager's feedback
- id (PK), manager_uid (FK), team_member_uid (FK)
- selected_strengths, selected_improvements (JSON arrays)
- feedback_text

## Privacy & Security

- **Local-first**: All data stays on your machine
- **No authentication**: Designed for single-user local execution
- **No telemetry**: No external API calls or cloud sync
- **Anonymous peer feedback**: Manager reports don't show who gave feedback
- **CSV includes provider ID**: For accountability during collection
- **.gitignore**: Protects REAL-*.csv, feedback.db, tenets.json

## Development

### Project Structure

```
.
├── feedback_app.py              # Flask application
├── feedback_models.py           # SQLAlchemy models
├── import_workday.py            # Workday XLSX import utility
├── import_orgchart.py           # Legacy orgchart CSV import
├── create_sample_data.py        # Sample data generator
├── feedback_templates/          # Jinja2 templates
├── tests/                       # Test suite
├── tenets-sample.json           # Sample tenets configuration
├── WORKDAY_INTEGRATION.md       # Workday integration design doc
└── README.md                    # This file
```

### Auto-Save Pattern

Used consistently across the application:
- 2-second debounce on all changes
- Visual "✓ Saved" indicator
- Silent error handling (logs to console)
- No manual save buttons or popups

### UI Patterns

- **Two-column layout**: Compact tenet selectors
- **Sortable tables**: Click headers to sort (↑↓)
- **Context banners**: Show current user/manager identity
- **Progress indicators**: Checklist with yellow → green states
- **Inline editing**: No separate forms or modals

## Troubleshooting

**Port conflict**
- Feedback tool uses port 5001
- Change in feedback_app.py if needed: `app.run(port=5002)`

**No managers found**
- Make sure orgchart CSV has people with direct reports
- Managers are auto-detected (people referenced in Manager UID column)

**Auto-save not working**
- Check browser console for errors
- Verify JavaScript is enabled
- Try hard refresh: Ctrl+Shift+R

**Butterfly chart not rendering**
- Check browser console for JavaScript errors
- Verify Chart.js CDN is accessible
- Try clearing browser cache

**Database locked**
- Close any other processes using feedback.db
- Restart the Flask app

## Contributing

This tool was developed with AI assistance (Claude Code by Anthropic) to accelerate development while maintaining code quality.

## License

MIT License - See LICENSE file for details

## Acknowledgments

- Sample employee names are tech-themed puns for demo purposes
- Butterfly chart pattern adapted from performance analytics tools
- Built with Flask, SQLAlchemy, and Chart.js
