# Feedback Tool - Quick Start Guide

## Quick Demo with Sample Data

**Want to try it out without real data?**

```bash
# Full demo setup (12 employees, 1 manager, with feedback)
python3 create_sample_feedback_data.py --demo

# Or for larger org (50 employees, 5 managers)
python3 create_sample_feedback_data.py --large --demo

# Start the app
python3 feedback_app.py
```

Access at: http://localhost:5001

Sample employees include: Paige Duty, Lee Latency, Mona Torr, Robin Rollback, Kenny Canary, and more!

## Setup (One-time)

1. **Import your organization's data**
   ```bash
   python3 import_orgchart.py REAL-orgchart-export.csv
   ```

   This creates `feedback.db` with all people from your orgchart.

2. **Start the application**
   ```bash
   python3 feedback_app.py
   ```

   Access at: http://localhost:5001

## Individual Workflow

1. Go to http://localhost:5001
2. Click "Start Giving Feedback"
3. Select your name from the dropdown
   - If you're not in the orgchart, select "[ Not in list - Enter custom ID ]"
   - Enter your User ID and optionally your name
4. For each colleague you want to provide feedback to:
   - Select their name (list is organized by manager for easier navigation)
   - Choose exactly 3 tenet strengths (two-column compact layout)
   - Choose 2-3 tenets for improvement
   - Add text explanations for both
   - Feedback auto-saves after 2 seconds (watch for "✓ Saved" indicator)
5. When done, click "Export Feedback CSVs"
6. Click "Download CSV" for each manager
7. Share downloaded CSV files with respective managers

## Manager Workflow

1. Go to http://localhost:5001
2. Click "Access Manager Tools"
3. Select your name from the dropdown
4. Drag & drop feedback CSV files onto the import area (multiple files supported)
   - Or click to browse and select files
   - Files import automatically and show per-file status
5. For each team member:
   - Click "View Report"
   - Review the butterfly chart (aggregated feedback)
   - Review anonymous peer comments
   - Select tenets to highlight in the report
   - Add your own feedback text (auto-saves)
   - Click "Export PDF" to download the report

## CSV Format

Individual feedback exports contain:
- From User ID (who gave the feedback)
- To User ID (who received it)
- Strengths (Tenet IDs) - comma-separated
- Improvements (Tenet IDs) - comma-separated
- Strengths Text
- Improvements Text

## Privacy Notes

- Individual CSV exports **include the provider's User ID**
- Manager's report view shows **anonymous** peer feedback
- Only manager's own feedback is attributed
- All data stays local (no cloud sync)

## UI Improvements

- **Auto-save**: Feedback saves automatically 2 seconds after changes (tenet selection or text input)
- **Compact layout**: Tenets displayed in two-column grid for better space usage
- **Organized recipients**: Colleague list grouped by manager using optgroups
- **External users**: Can provide feedback even if not in the orgchart
- **Browser downloads**: CSV files download directly through browser (no server-side files)

## Troubleshooting

**"No user selected" error**
- Make sure you selected your name from the dropdown first
- If not in list, use the custom ID option

**"Team member not found or not in your team"**
- Verify the orgchart has correct manager relationships
- Re-import if needed: `python3 import_orgchart.py REAL-orgchart-export.csv`

**Port conflict**
- Feedback tool runs on port 5001 (bonus tool uses 5000)
- If port 5001 is busy, edit `feedback_app.py` last line to change port

**Database locked**
- Close any other processes using `feedback.db`
- Restart the Flask app

**Auto-save not working**
- Check browser console for errors
- Verify you've selected both tenets and added text
- Manual save still available via "Save Feedback" button
