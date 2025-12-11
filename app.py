"""
Team Feedback Tool - Flask Application

Routes:
- / : Home page (select mode: individual or manager)
- /individual : Individual feedback collection
- /individual/export : Export feedback CSVs per manager
- /manager : Manager feedback dashboard
- /manager/import : Import feedback CSVs
- /manager/report/<user_id> : View/edit report for team member
- /manager/export-pdf/<user_id> : Export PDF report
"""

from flask import Flask, render_template, request, jsonify, send_file, session as flask_session, redirect
from feedback_models import init_db, Person, Feedback, ManagerFeedback, WorkdayFeedback, name_to_user_id
from scripts.import_workday import import_workday_xlsx, get_available_date_ranges
import json
import csv
import io
import os
import base64
import tempfile
from collections import defaultdict
from sqlalchemy import func
from weasyprint import HTML, CSS
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from datetime import datetime
from dateutil.relativedelta import relativedelta

app = Flask(__name__, template_folder='feedback_templates')
app.secret_key = 'feedback-tool-secret-key-change-in-production'

# Load tenets configuration
# Prefer tenets.json (org-specific), fall back to samples/tenets-sample.json
TENETS_FILE = 'tenets.json' if os.path.exists('tenets.json') else 'samples/tenets-sample.json'


def load_tenets():
    """Load tenets from JSON file (tenets.json if exists, else samples/tenets-sample.json)"""
    with open(TENETS_FILE, 'r') as f:
        data = json.load(f)
    return [t for t in data['tenets'] if t.get('active', True)]


@app.route('/')
def index():
    """Home page - select mode"""
    return render_template('index.html')


@app.route('/feedback')
def feedback_for_workday():
    """Streamlined feedback page for Workday workflow.

    Accepts optional 'for' query parameter with recipient name.
    URL can be shared directly: /feedback?for=Robin%20Rollback
    """
    recipient_name = request.args.get('for', '').strip()
    tenets = load_tenets()

    return render_template('feedback.html',
                          recipient_name=recipient_name if recipient_name else None,
                          tenets=tenets)


@app.route('/api/db-stats')
def get_db_stats():
    """Get database statistics for home page"""
    session = init_db()

    total_people = session.query(Person).count()
    managers = session.query(Person).filter(Person.direct_reports.any()).count()
    team_members = total_people - managers
    peer_feedback = session.query(Feedback).count()
    manager_reviews = session.query(ManagerFeedback).count()

    session.close()

    return jsonify({
        "success": True,
        "total_people": total_people,
        "managers": managers,
        "team_members": team_members,
        "peer_feedback": peer_feedback,
        "manager_reviews": manager_reviews
    })


@app.route('/api/import-orgchart', methods=['POST'])
def import_orgchart_web():
    """Import orgchart CSV via web interface"""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    reset_db = request.form.get('reset', 'false').lower() == 'true'

    session = init_db()

    try:
        # Read CSV
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)

        # Validate required columns
        required_cols = ['Name', 'User ID', 'Job Title', 'Email', 'Manager UID']
        if reader.fieldnames is None:
            session.close()
            return jsonify({"success": False, "error": "Empty or invalid CSV file"}), 400

        missing_cols = [col for col in required_cols if col not in reader.fieldnames]
        if missing_cols:
            session.close()
            return jsonify({
                "success": False,
                "error": f"Invalid CSV format. Missing columns: {', '.join(missing_cols)}"
            }), 400

        if reset_db:
            # Clear all data
            session.query(ManagerFeedback).delete()
            session.query(Feedback).delete()
            session.query(Person).delete()
            # Clear user sessions since those users no longer exist
            flask_session.pop('user_id', None)
            flask_session.pop('manager_uid', None)

        # Import people
        count = 0
        updated = 0
        for row in reader:
            user_id = row['User ID']
            existing = session.query(Person).filter_by(user_id=user_id).first()

            if existing:
                # Update existing person
                existing.name = row['Name']
                existing.job_title = row['Job Title']
                existing.email = row['Email']
                existing.location = row.get('Location', '')
                existing.manager_uid = row['Manager UID'] if row['Manager UID'] else None
                updated += 1
            else:
                # Create new person
                person = Person(
                    user_id=user_id,
                    name=row['Name'],
                    job_title=row['Job Title'],
                    email=row['Email'],
                    location=row.get('Location', ''),
                    manager_uid=row['Manager UID'] if row['Manager UID'] else None
                )
                session.add(person)
                count += 1

        session.commit()
        session.close()

        return jsonify({
            "success": True,
            "new_count": count,
            "updated_count": updated,
            "reset": reset_db
        })

    except Exception as e:
        session.close()
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/individual')
def individual_feedback():
    """Individual feedback collection page"""
    current_user_id = flask_session.get('user_id')

    # If no user selected, show selection page
    if not current_user_id:
        session = init_db()
        all_people = session.query(Person).order_by(Person.name).all()
        session.close()
        return render_template('individual_select.html', all_people=[p.to_dict() for p in all_people])

    # User selected - show feedback page
    session = init_db()
    current_user = session.query(Person).filter_by(user_id=current_user_id).first()

    # If not in database, create a mock user object (external provider)
    if not current_user:
        current_user = type('obj', (object,), {
            'user_id': current_user_id,
            'name': current_user_id,
            'email': '',
            'job_title': 'External'
        })

    # Get all people (for feedback recipients)
    all_people = session.query(Person).order_by(Person.name).all()

    # Group people by manager for organized dropdown
    people_by_manager = []
    manager_groups = defaultdict(list)

    for person in all_people:
        if person.manager_uid:
            manager_groups[person.manager_uid].append(person.to_dict())
        else:
            # Top-level (no manager)
            manager_groups['__TOP__'].append(person.to_dict())

    # Build grouped structure
    for manager_uid, people in manager_groups.items():
        if manager_uid == '__TOP__':
            manager_name = 'No Manager / Top Level'
        else:
            manager = session.query(Person).filter_by(user_id=manager_uid).first()
            manager_name = f"{manager.name} ({manager_uid})" if manager else manager_uid

        people_by_manager.append({
            'manager_uid': manager_uid,
            'manager_name': manager_name,
            'people': sorted(people, key=lambda x: x['name'])
        })

    # Sort groups by manager name
    people_by_manager.sort(key=lambda x: x['manager_name'])

    # Get existing feedback given by current user
    existing_feedback = []
    if current_user_id:
        existing_feedback = session.query(Feedback).filter_by(
            from_user_id=current_user_id
        ).all()

    tenets = load_tenets()
    session.close()

    return render_template(
        'individual_feedback.html',
        current_user=current_user,
        all_people=[p.to_dict() for p in all_people],
        people_by_manager=people_by_manager,
        existing_feedback=[f.to_dict() for f in existing_feedback],
        tenets=tenets
    )


@app.route('/individual/<user_id>')
def individual_login(user_id):
    """Direct individual login via URL - sets session and redirects to feedback page"""
    # Allow any user_id (even if not in database) for external providers
    flask_session['user_id'] = user_id
    return redirect('/individual')


@app.route('/individual/switch')
def individual_switch():
    """Clear user session and return to selection"""
    flask_session.pop('user_id', None)
    return redirect('/individual')


@app.route('/api/set-user', methods=['POST'])
def set_user():
    """Set current user in session - allows custom user IDs not in database"""
    data = request.get_json()
    user_id = data.get('user_id')

    if not user_id:
        return jsonify({"success": False, "error": "Missing user_id"}), 400

    # Allow any user_id, even if not in database
    # This supports external feedback providers
    flask_session['user_id'] = user_id
    return jsonify({"success": True})


@app.route('/api/feedback', methods=['POST'])
def save_feedback():
    """Save individual feedback"""
    data = request.get_json()

    from_user_id = flask_session.get('user_id')
    if not from_user_id:
        return jsonify({"success": False, "error": "No user selected"}), 400

    to_user_id = data.get('to_user_id')
    strengths = data.get('strengths', [])
    improvements = data.get('improvements', [])
    strengths_text = data.get('strengths_text', '')
    improvements_text = data.get('improvements_text', '')

    if not to_user_id:
        return jsonify({"success": False, "error": "Missing to_user_id"}), 400

    # Validate tenet counts
    if len(strengths) != 3:
        return jsonify({"success": False, "error": "Must select exactly 3 strengths"}), 400

    if len(improvements) < 2 or len(improvements) > 3:
        return jsonify({"success": False, "error": "Must select 2-3 improvements"}), 400

    session = init_db()

    # Check if feedback already exists
    feedback = session.query(Feedback).filter_by(
        from_user_id=from_user_id,
        to_user_id=to_user_id
    ).first()

    if feedback:
        # Update existing
        feedback.set_strengths(strengths)
        feedback.set_improvements(improvements)
        feedback.strengths_text = strengths_text
        feedback.improvements_text = improvements_text
    else:
        # Create new
        feedback = Feedback(
            from_user_id=from_user_id,
            to_user_id=to_user_id
        )
        feedback.set_strengths(strengths)
        feedback.set_improvements(improvements)
        feedback.strengths_text = strengths_text
        feedback.improvements_text = improvements_text
        session.add(feedback)

    session.commit()
    session.close()

    return jsonify({"success": True})


@app.route('/api/feedback/<to_user_id>', methods=['DELETE'])
def delete_feedback(to_user_id):
    """Delete feedback for a specific person"""
    from_user_id = flask_session.get('user_id')
    if not from_user_id:
        return jsonify({"success": False, "error": "No user selected"}), 400

    session = init_db()
    feedback = session.query(Feedback).filter_by(
        from_user_id=from_user_id,
        to_user_id=to_user_id
    ).first()

    if feedback:
        session.delete(feedback)
        session.commit()

    session.close()
    return jsonify({"success": True})


@app.route('/individual/export-list')
def export_feedback_list():
    """Show list of managers to export feedback for"""
    current_user_id = flask_session.get('user_id')
    if not current_user_id:
        return "Please select your user ID first", 400

    session = init_db()

    # Get all feedback from current user
    feedbacks = session.query(Feedback).filter_by(from_user_id=current_user_id).all()

    if not feedbacks:
        session.close()
        return "No feedback to export", 400

    # Group by manager
    feedback_by_manager = defaultdict(list)

    for feedback in feedbacks:
        receiver = session.query(Person).filter_by(user_id=feedback.to_user_id).first()
        if receiver and receiver.manager_uid:
            feedback_by_manager[receiver.manager_uid].append({
                'feedback': feedback,
                'receiver': receiver
            })

    # Build list of managers with feedback counts and associate names
    export_list = []
    for manager_uid, feedback_list in feedback_by_manager.items():
        manager = session.query(Person).filter_by(user_id=manager_uid).first()

        # Get list of unique associates (receivers)
        associates = list({item['receiver'].name for item in feedback_list})
        associates.sort()

        export_list.append({
            'manager_uid': manager_uid,
            'manager_name': manager.name if manager else manager_uid,
            'feedback_count': len(feedback_list),
            'associates': associates
        })

    session.close()

    return render_template('export_list.html', export_list=export_list)


@app.route('/individual/export/<manager_uid>')
def export_feedback_csv(manager_uid):
    """Export feedback CSV for a specific manager - downloads through browser"""
    current_user_id = flask_session.get('user_id')
    if not current_user_id:
        return "Please select your user ID first", 400

    session = init_db()

    # Get all feedback from current user to people managed by this manager
    feedbacks = session.query(Feedback).filter_by(from_user_id=current_user_id).all()

    feedback_list = []
    for feedback in feedbacks:
        receiver = session.query(Person).filter_by(user_id=feedback.to_user_id).first()
        if receiver and receiver.manager_uid == manager_uid:
            feedback_list.append(feedback)

    if not feedback_list:
        session.close()
        return "No feedback for this manager", 400

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'From User ID',
        'To User ID',
        'Strengths (Tenet IDs)',
        'Improvements (Tenet IDs)',
        'Strengths Text',
        'Improvements Text'
    ])

    for fb in feedback_list:
        writer.writerow([
            fb.from_user_id,
            fb.to_user_id,
            ','.join(fb.get_strengths()),
            ','.join(fb.get_improvements()),
            fb.strengths_text,
            fb.improvements_text
        ])

    session.close()

    # Convert to bytes for download
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'feedback_for_{manager_uid}.csv'
    )


@app.route('/manager')
def manager_dashboard():
    """Manager dashboard - view team and feedback.

    Supports two modes:
    1. Name-based (Workday workflow): ?name=Manager%20Name or session['manager_name']
       - Team derived from Workday feedback recipients
    2. UID-based (orgchart workflow): session['manager_uid']
       - Team derived from orgchart direct reports
    """
    # Check for name parameter (Workday workflow)
    manager_name = request.args.get('name', '').strip()
    if manager_name:
        flask_session['manager_name'] = manager_name
        flask_session.pop('manager_uid', None)  # Clear UID-based session
        return redirect('/manager')

    # Check session for manager identity
    manager_name = flask_session.get('manager_name')
    manager_uid = flask_session.get('manager_uid')

    # If no manager selected, show selection page
    if not manager_name and not manager_uid:
        session = init_db()
        # Get all managers from orgchart (if any)
        managers = session.query(Person).filter(Person.direct_reports.any()).order_by(Person.name).all()
        session.close()
        return render_template('manager_select.html', managers=[m.to_dict() for m in managers])

    session = init_db()
    team_members = []
    manager_info = {}
    has_orgchart = False

    if manager_uid:
        # UID-based workflow (from orgchart)
        manager = session.query(Person).filter_by(user_id=manager_uid).first()
        if not manager:
            flask_session.pop('manager_uid', None)
            session.close()
            return redirect('/manager')

        manager_info = manager.to_dict()
        manager_name = manager.name
        has_orgchart = True

        # Get team from orgchart
        team_members_objs = session.query(Person).filter_by(manager_uid=manager_uid).all()
        for tm in team_members_objs:
            tm_dict = tm.to_dict()
            # Count legacy feedback
            tm_dict['feedback_count'] = session.query(Feedback).filter_by(to_user_id=tm.user_id).count()
            # Count Workday feedback
            tm_dict['wd_feedback_count'] = session.query(WorkdayFeedback).filter(
                WorkdayFeedback.about == tm.name
            ).count()
            team_members.append(tm_dict)

    else:
        # Name-based workflow (Workday)
        # Check if manager exists in orgchart for enrichment
        manager_person = session.query(Person).filter_by(name=manager_name).first()
        if manager_person:
            manager_info = manager_person.to_dict()
            has_orgchart = True
        else:
            # Use derived ID for manager
            manager_info = {
                'name': manager_name,
                'user_id': name_to_user_id(manager_name),
                'job_title': None,
                'email': None
            }

        # Get team members from Workday feedback recipients
        # Find all unique "about" names from Workday feedback
        wd_recipients = session.query(
            WorkdayFeedback.about,
            func.count(WorkdayFeedback.id).label('count')
        ).group_by(WorkdayFeedback.about).all()

        for recipient_name, count in wd_recipients:
            # Try to find in orgchart for enrichment
            person = session.query(Person).filter_by(name=recipient_name).first()
            if person:
                tm_dict = person.to_dict()
                tm_dict['feedback_count'] = session.query(Feedback).filter_by(to_user_id=person.user_id).count()
            else:
                # Create entry with derived ID from name
                tm_dict = {
                    'name': recipient_name,
                    'user_id': name_to_user_id(recipient_name),
                    'job_title': None,
                    'email': None,
                    'feedback_count': 0
                }
            tm_dict['wd_feedback_count'] = count
            team_members.append(tm_dict)

    session.close()

    return render_template(
        'manager_dashboard.html',
        manager=manager_info,
        team_members=team_members,
        has_orgchart=has_orgchart
    )


@app.route('/api/team-butterfly-data')
def get_team_butterfly_data():
    """Get aggregated butterfly chart data for entire team.

    Supports two modes:
    1. UID-based (orgchart workflow): Uses manager_uid from session
    2. Name-based (Workday workflow): Uses manager_name from session
    """
    manager_uid = flask_session.get('manager_uid')
    manager_name = flask_session.get('manager_name')

    if not manager_uid and not manager_name:
        return jsonify({"success": False, "error": "No manager selected"}), 400

    session = init_db()

    # Aggregate tenet counts across all team members
    tenet_strengths = defaultdict(int)
    tenet_improvements = defaultdict(int)

    if manager_uid:
        # UID-based workflow (from orgchart)
        team_members = session.query(Person).filter_by(manager_uid=manager_uid).all()
        team_member_ids = [tm.user_id for tm in team_members]
        team_member_names = [tm.name for tm in team_members]

        # Get legacy feedback for team members
        all_feedbacks = session.query(Feedback).filter(Feedback.to_user_id.in_(team_member_ids)).all()

        for fb in all_feedbacks:
            for tenet_id in fb.get_strengths():
                tenet_strengths[tenet_id] += 1
            for tenet_id in fb.get_improvements():
                tenet_improvements[tenet_id] += 1

        # Add manager's own feedback for each team member
        manager_feedbacks = session.query(ManagerFeedback).filter_by(manager_uid=manager_uid).all()
        for mfb in manager_feedbacks:
            for tenet_id in mfb.get_selected_strengths():
                tenet_strengths[tenet_id] += 1
            for tenet_id in mfb.get_selected_improvements():
                tenet_improvements[tenet_id] += 1

        # Also include Workday structured feedback for team members
        wd_feedbacks = session.query(WorkdayFeedback).filter(
            WorkdayFeedback.about.in_(team_member_names),
            WorkdayFeedback.is_structured == 1
        ).all()

        for fb in wd_feedbacks:
            for tenet_id in fb.get_strengths():
                tenet_strengths[tenet_id] += 1
            for tenet_id in fb.get_improvements():
                tenet_improvements[tenet_id] += 1

    else:
        # Name-based workflow (Workday only)
        # Get team from Workday feedback recipients
        wd_recipients = session.query(WorkdayFeedback.about).distinct().all()
        team_member_names = [r.about for r in wd_recipients]

        # Get structured Workday feedback for all recipients
        wd_feedbacks = session.query(WorkdayFeedback).filter(
            WorkdayFeedback.is_structured == 1
        ).all()

        for fb in wd_feedbacks:
            for tenet_id in fb.get_strengths():
                tenet_strengths[tenet_id] += 1
            for tenet_id in fb.get_improvements():
                tenet_improvements[tenet_id] += 1

    tenets = load_tenets()

    # Build butterfly chart data
    butterfly_data = []
    for tenet in tenets:
        butterfly_data.append({
            'id': tenet['id'],
            'name': tenet['name'],
            'strength_count': tenet_strengths.get(tenet['id'], 0),
            'improvement_count': tenet_improvements.get(tenet['id'], 0)
        })

    # Sort by net score
    butterfly_data.sort(key=lambda x: (x['strength_count'] - x['improvement_count']), reverse=True)

    session.close()

    return jsonify({
        "success": True,
        "butterfly_data": butterfly_data
    })


@app.route('/manager/<manager_uid>')
def manager_login(manager_uid):
    """Direct manager login via URL - sets session and redirects to dashboard"""
    session = init_db()
    manager = session.query(Person).filter_by(user_id=manager_uid).first()
    session.close()

    if not manager:
        return "Manager not found", 404

    # Set manager in session
    flask_session['manager_uid'] = manager_uid

    # Redirect to dashboard
    return redirect('/manager')


@app.route('/manager/switch')
def manager_switch():
    """Clear manager session and return to selection"""
    flask_session.pop('manager_uid', None)
    flask_session.pop('manager_name', None)
    return redirect('/manager')


@app.route('/api/set-manager', methods=['POST'])
def set_manager():
    """Set current manager in session"""
    data = request.get_json()
    manager_uid = data.get('manager_uid')

    if not manager_uid:
        return jsonify({"success": False, "error": "Missing manager_uid"}), 400

    session = init_db()
    manager = session.query(Person).filter_by(user_id=manager_uid).first()
    session.close()

    if not manager:
        return jsonify({"success": False, "error": "Manager not found"}), 404

    flask_session['manager_uid'] = manager_uid
    return jsonify({"success": True})


@app.route('/manager/import', methods=['POST'])
def import_feedback_csv():
    """Import feedback CSV file"""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    session = init_db()

    try:
        # Read CSV
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)

        # Validate required columns
        required_cols = ['From User ID', 'To User ID', 'Strengths (Tenet IDs)',
                         'Improvements (Tenet IDs)', 'Strengths Text', 'Improvements Text']
        if reader.fieldnames is None:
            session.close()
            return jsonify({"success": False, "error": "Empty or invalid CSV file"}), 400

        missing_cols = [col for col in required_cols if col not in reader.fieldnames]
        if missing_cols:
            session.close()
            return jsonify({
                "success": False,
                "error": f"Invalid CSV format. Missing columns: {', '.join(missing_cols)}"
            }), 400

        new_count = 0
        updated_count = 0
        updated_pairs = []

        for row in reader:
            from_user_id = row['From User ID']
            to_user_id = row['To User ID']
            strengths = row['Strengths (Tenet IDs)'].split(',') if row['Strengths (Tenet IDs)'] else []
            improvements = row['Improvements (Tenet IDs)'].split(',') if row['Improvements (Tenet IDs)'] else []

            # Check if already exists
            existing = session.query(Feedback).filter_by(
                from_user_id=from_user_id,
                to_user_id=to_user_id
            ).first()

            if existing:
                # Update existing record
                existing.strengths_text = row['Strengths Text']
                existing.improvements_text = row['Improvements Text']
                existing.set_strengths(strengths)
                existing.set_improvements(improvements)
                updated_count += 1
                updated_pairs.append(f"{from_user_id} → {to_user_id}")
            else:
                feedback = Feedback(
                    from_user_id=from_user_id,
                    to_user_id=to_user_id,
                    strengths_text=row['Strengths Text'],
                    improvements_text=row['Improvements Text']
                )
                feedback.set_strengths(strengths)
                feedback.set_improvements(improvements)
                session.add(feedback)
                new_count += 1

        session.commit()
        session.close()

        return jsonify({
            "success": True,
            "new_count": new_count,
            "updated_count": updated_count,
            "updated_pairs": updated_pairs
        })

    except Exception as e:
        session.close()
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/manager/import-xlsx', methods=['POST'])
def import_workday_xlsx_route():
    """Import feedback from Workday XLSX export"""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    if not file.filename.endswith('.xlsx'):
        return jsonify({"success": False, "error": "File must be an XLSX file"}), 400

    # Save to temporary file for processing
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        result = import_workday_xlsx(tmp_path)
        return jsonify(result.to_dict())
    finally:
        # Clean up temp file
        os.unlink(tmp_path)


@app.route('/api/workday-feedback')
def get_workday_feedback():
    """Get Workday feedback with optional date filtering.

    Query params:
    - about: Filter by recipient name (optional)
    - start_date: ISO date string for start of range (optional)
    - end_date: ISO date string for end of range (optional)
    - period: Shortcut for date range - 'all', '3m' (default), '6m', '12m'
    """
    about = request.args.get('about')
    period = request.args.get('period', '3m')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    session = init_db()

    query = session.query(WorkdayFeedback)

    # Filter by recipient if specified
    if about:
        query = query.filter(WorkdayFeedback.about == about)

    # Date filtering
    if start_date_str and end_date_str:
        # Custom date range
        try:
            start_date = datetime.fromisoformat(start_date_str)
            end_date = datetime.fromisoformat(end_date_str)
            query = query.filter(
                WorkdayFeedback.date >= start_date,
                WorkdayFeedback.date <= end_date
            )
        except ValueError:
            session.close()
            return jsonify({"success": False, "error": "Invalid date format"}), 400
    elif period != 'all':
        # Period-based filtering (default: current month + 3 previous months)
        now = datetime.now()
        end_date = now

        if period == '3m':
            start_date = now - relativedelta(months=3)
        elif period == '6m':
            start_date = now - relativedelta(months=6)
        elif period == '12m':
            start_date = now - relativedelta(months=12)
        else:
            start_date = now - relativedelta(months=3)  # Default

        query = query.filter(
            WorkdayFeedback.date >= start_date,
            WorkdayFeedback.date <= end_date
        )

    # Order by date descending
    query = query.order_by(WorkdayFeedback.date.desc())

    feedbacks = query.all()
    session.close()

    return jsonify({
        "success": True,
        "feedbacks": [fb.to_dict() for fb in feedbacks],
        "total": len(feedbacks)
    })


@app.route('/api/workday-feedback/recipients')
def get_workday_recipients():
    """Get list of unique recipients with feedback counts"""
    session = init_db()

    # Get unique recipients with counts
    results = session.query(
        WorkdayFeedback.about,
        func.count(WorkdayFeedback.id).label('total_count'),
        func.sum(WorkdayFeedback.is_structured).label('structured_count')
    ).group_by(WorkdayFeedback.about).order_by(WorkdayFeedback.about).all()

    recipients = []
    for row in results:
        recipients.append({
            'name': row.about,
            'total_count': row.total_count,
            'structured_count': row.structured_count or 0,
            'generic_count': row.total_count - (row.structured_count or 0)
        })

    session.close()

    return jsonify({
        "success": True,
        "recipients": recipients
    })


@app.route('/api/workday-feedback/date-ranges')
def get_date_ranges():
    """Get available date ranges for filtering"""
    ranges = get_available_date_ranges()

    return jsonify({
        "success": True,
        "ranges": [
            {"year": r[0], "month": r[1], "count": r[2]}
            for r in ranges
        ]
    })


@app.route('/manager/report/<user_id>')
@app.route('/manager/report')
def view_report(user_id=None):
    """View feedback report for team member.

    Supports multiple access modes:
    1. Real user_id: /manager/report/emp001 (orgchart-based)
    2. Derived user_id: /manager/report/wd_a1b2c3d4 (Workday-only)
    3. Name query param: /manager/report?name=Robin%20Rollback (legacy)
    """
    manager_uid = flask_session.get('manager_uid')
    manager_name = flask_session.get('manager_name')

    if not manager_uid and not manager_name:
        return "Please access via the manager dashboard first", 400

    # Get team member name from query param if no user_id
    team_member_name = request.args.get('name', '').strip() if not user_id else None

    if not user_id and not team_member_name:
        return "Missing team member identifier", 400

    session = init_db()

    # Initialize team member info
    team_member_info = None
    team_member_user_id = user_id

    # Check if this is a derived ID (starts with 'wd_')
    is_derived_id = user_id and user_id.startswith('wd_')

    if user_id and not is_derived_id:
        # Real user_id from orgchart
        team_member = session.query(Person).filter_by(user_id=user_id).first()
        if not team_member:
            session.close()
            return "Team member not found", 404

        # Verify team membership if using orgchart workflow
        if manager_uid and team_member.manager_uid != manager_uid:
            session.close()
            return "Team member not in your team", 403

        team_member_info = team_member.to_dict()
        team_member_name = team_member.name

    elif user_id and is_derived_id:
        # Derived ID from Workday - find the name from Workday feedback
        # Look for a recipient whose derived ID matches
        wd_recipient = session.query(WorkdayFeedback.about).distinct().all()
        for (name,) in wd_recipient:
            if name_to_user_id(name) == user_id:
                team_member_name = name
                break

        if not team_member_name:
            session.close()
            return "Team member not found", 404

        # Try to find in orgchart for enrichment
        team_member = session.query(Person).filter_by(name=team_member_name).first()
        if team_member:
            team_member_info = team_member.to_dict()
        else:
            team_member_info = {
                'name': team_member_name,
                'user_id': user_id,
                'job_title': None,
                'email': None
            }

    else:
        # Name-based access (legacy query param)
        # Try to find in orgchart for enrichment
        team_member = session.query(Person).filter_by(name=team_member_name).first()
        if team_member:
            team_member_info = team_member.to_dict()
            team_member_user_id = team_member.user_id
        else:
            team_member_user_id = name_to_user_id(team_member_name)
            team_member_info = {
                'name': team_member_name,
                'user_id': team_member_user_id,
                'job_title': None,
                'email': None
            }

    # Get legacy feedback (only if not a derived ID)
    feedbacks = []
    if team_member_user_id and not team_member_user_id.startswith('wd_'):
        feedbacks = session.query(Feedback).filter_by(to_user_id=team_member_user_id).all()

    # Get Workday feedback by name (both structured and generic)
    wd_feedbacks = session.query(WorkdayFeedback).filter(
        WorkdayFeedback.about == team_member_name
    ).order_by(WorkdayFeedback.date.desc()).all()

    # Separate structured vs generic Workday feedback
    wd_structured = [fb for fb in wd_feedbacks if fb.is_structured]
    wd_generic = [fb for fb in wd_feedbacks if not fb.is_structured]

    # Aggregate tenet counts from legacy feedback
    tenet_strengths = defaultdict(int)
    tenet_improvements = defaultdict(int)

    for fb in feedbacks:
        for tenet_id in fb.get_strengths():
            tenet_strengths[tenet_id] += 1
        for tenet_id in fb.get_improvements():
            tenet_improvements[tenet_id] += 1

    # Add structured Workday feedback to tenet counts
    for fb in wd_structured:
        for tenet_id in fb.get_strengths():
            tenet_strengths[tenet_id] += 1
        for tenet_id in fb.get_improvements():
            tenet_improvements[tenet_id] += 1

    # Get manager's own feedback
    # Use manager_uid or derived ID from manager_name
    effective_manager_uid = manager_uid or name_to_user_id(manager_name)

    manager_feedback = None
    if team_member_user_id and effective_manager_uid:
        manager_feedback = session.query(ManagerFeedback).filter_by(
            manager_uid=effective_manager_uid,
            team_member_uid=team_member_user_id
        ).first()

    # Add manager's selections to the counts (manager's input counts as +1)
    if manager_feedback:
        for tenet_id in manager_feedback.get_selected_strengths():
            tenet_strengths[tenet_id] += 1
        for tenet_id in manager_feedback.get_selected_improvements():
            tenet_improvements[tenet_id] += 1

    tenets = load_tenets()

    # Build butterfly chart data
    butterfly_data = []
    for tenet in tenets:
        butterfly_data.append({
            'id': tenet['id'],
            'name': tenet['name'],
            'strength_count': tenet_strengths.get(tenet['id'], 0),
            'improvement_count': tenet_improvements.get(tenet['id'], 0)
        })

    # Sort by net score
    butterfly_data.sort(key=lambda x: (x['strength_count'] - x['improvement_count']), reverse=True)

    # Prepare legacy feedback with giver names for manager view (non-anonymous)
    feedbacks_with_names = []
    for fb in feedbacks:
        fb_dict = fb.to_dict()
        # Get giver's name
        giver = session.query(Person).filter_by(user_id=fb.from_user_id).first()
        fb_dict['from_name'] = giver.name if giver else fb.from_user_id
        fb_dict['source'] = 'legacy'
        feedbacks_with_names.append(fb_dict)

    # Add structured Workday feedback
    for fb in wd_structured:
        fb_dict = fb.to_dict()
        fb_dict['from_name'] = fb.from_name
        fb_dict['source'] = 'workday_structured'
        feedbacks_with_names.append(fb_dict)

    session.close()

    return render_template(
        'report.html',
        team_member=team_member_info,
        feedbacks=feedbacks_with_names,
        generic_feedbacks=[fb.to_dict() for fb in wd_generic],
        butterfly_data=butterfly_data,
        manager_feedback=manager_feedback.to_dict() if manager_feedback else None,
        tenets=tenets
    )


@app.route('/api/manager-feedback', methods=['POST'])
def save_manager_feedback():
    """Save manager's own feedback.

    Supports both orgchart-based (manager_uid from session) and
    Workday-based (derived ID from manager_name) workflows.
    """
    data = request.get_json()

    manager_uid = flask_session.get('manager_uid')
    manager_name = flask_session.get('manager_name')

    if not manager_uid and not manager_name:
        return jsonify({"success": False, "error": "No manager selected"}), 400

    # Use real manager_uid or derive from name
    effective_manager_uid = manager_uid or name_to_user_id(manager_name)

    team_member_uid = data.get('team_member_uid')
    selected_strengths = data.get('selected_strengths', [])
    selected_improvements = data.get('selected_improvements', [])
    feedback_text = data.get('feedback_text', '')

    if not team_member_uid:
        return jsonify({"success": False, "error": "Missing team_member_uid"}), 400

    # Enforce mutual exclusivity: remove any tenets that appear in both lists
    overlap = set(selected_strengths) & set(selected_improvements)
    if overlap:
        # Remove overlapping tenets from both lists to enforce mutual exclusivity
        selected_strengths = [t for t in selected_strengths if t not in overlap]
        selected_improvements = [t for t in selected_improvements if t not in overlap]

    session = init_db()

    # Check if exists
    mgr_feedback = session.query(ManagerFeedback).filter_by(
        manager_uid=effective_manager_uid,
        team_member_uid=team_member_uid
    ).first()

    if mgr_feedback:
        # Update
        mgr_feedback.set_selected_strengths(selected_strengths)
        mgr_feedback.set_selected_improvements(selected_improvements)
        mgr_feedback.feedback_text = feedback_text
    else:
        # Create
        mgr_feedback = ManagerFeedback(
            manager_uid=effective_manager_uid,
            team_member_uid=team_member_uid,
            feedback_text=feedback_text
        )
        mgr_feedback.set_selected_strengths(selected_strengths)
        mgr_feedback.set_selected_improvements(selected_improvements)
        session.add(mgr_feedback)

    session.commit()
    session.close()

    return jsonify({"success": True})


def generate_butterfly_chart_image(butterfly_data, manager_selected_strengths, manager_selected_improvements):
    """
    Generate butterfly chart as base64-encoded PNG image using matplotlib

    Args:
        butterfly_data: List of dicts with tenet data
        manager_selected_strengths: List of tenet IDs selected by manager
        manager_selected_improvements: List of tenet IDs selected by manager

    Returns:
        Base64-encoded PNG image string
    """
    if not butterfly_data:
        # Return empty/placeholder image
        fig, ax = plt.subplots(figsize=(10, 1))
        ax.text(0.5, 0.5, 'No feedback data available', ha='center', va='center')
        ax.axis('off')
    else:
        # Prepare data
        tenet_names = [t['name'] for t in butterfly_data]
        strength_counts = [t['strength_count'] for t in butterfly_data]
        improvement_counts = [-t['improvement_count'] for t in butterfly_data]  # Negative for left side

        # Determine which bars should be highlighted
        strength_colors = []
        improvement_colors = []

        for t in butterfly_data:
            is_strength_selected = t['id'] in manager_selected_strengths
            is_improvement_selected = t['id'] in manager_selected_improvements

            strength_colors.append('#51cf66' if is_strength_selected else '#28a745')
            improvement_colors.append('#ff6b6b' if is_improvement_selected else '#dc3545')

        # Create figure
        fig_height = max(6, len(butterfly_data) * 0.4)
        fig, ax = plt.subplots(figsize=(10, fig_height))

        # Create horizontal bar chart
        y_pos = range(len(tenet_names))

        # Plot improvements (left, negative values)
        bars_left = ax.barh(y_pos, improvement_counts, color=improvement_colors,
                           edgecolor='black', linewidth=0.5)

        # Plot strengths (right, positive values)
        bars_right = ax.barh(y_pos, strength_counts, color=strength_colors,
                            edgecolor='black', linewidth=0.5)

        # Highlight manager-selected bars with thicker border
        for i, t in enumerate(butterfly_data):
            if t['id'] in manager_selected_improvements:
                bars_left[i].set_linewidth(2.5)
                bars_left[i].set_edgecolor('#ff0000')
            if t['id'] in manager_selected_strengths:
                bars_right[i].set_linewidth(2.5)
                bars_right[i].set_edgecolor('#00ff00')

        # Set labels
        ax.set_yticks(y_pos)
        ax.set_yticklabels(tenet_names)
        ax.set_xlabel('Count')
        ax.axvline(x=0, color='black', linewidth=1)

        # Invert y-axis so highest scores (strengths) appear at top
        ax.invert_yaxis()

        ax.set_title('Team Tenets - Butterfly Chart\n(Strengths right, Improvements left)',
                     fontsize=12, fontweight='bold')

        plt.tight_layout()

    # Convert to base64
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    plt.close(fig)

    return image_base64


@app.route('/manager/export-pdf/<user_id>')
def export_pdf_report(user_id):
    """Export feedback report as PDF"""
    manager_uid = flask_session.get('manager_uid')
    if not manager_uid:
        return "Please select your manager ID first", 400

    session = init_db()

    # Get team member
    team_member = session.query(Person).filter_by(user_id=user_id).first()
    if not team_member or team_member.manager_uid != manager_uid:
        session.close()
        return "Team member not found or not in your team", 403

    # Get manager info
    manager = session.query(Person).filter_by(user_id=manager_uid).first()

    # Get all feedback for this person
    feedbacks = session.query(Feedback).filter_by(to_user_id=user_id).all()

    # Aggregate tenet counts
    tenet_strengths = defaultdict(int)
    tenet_improvements = defaultdict(int)

    for fb in feedbacks:
        for tenet_id in fb.get_strengths():
            tenet_strengths[tenet_id] += 1
        for tenet_id in fb.get_improvements():
            tenet_improvements[tenet_id] += 1

    # Get manager's own feedback
    manager_feedback = session.query(ManagerFeedback).filter_by(
        manager_uid=manager_uid,
        team_member_uid=user_id
    ).first()

    # Add manager's selections to the counts
    manager_selected_strengths = []
    manager_selected_improvements = []

    if manager_feedback:
        manager_selected_strengths = manager_feedback.get_selected_strengths()
        manager_selected_improvements = manager_feedback.get_selected_improvements()

        for tenet_id in manager_selected_strengths:
            tenet_strengths[tenet_id] += 1
        for tenet_id in manager_selected_improvements:
            tenet_improvements[tenet_id] += 1

    tenets = load_tenets()

    # Build butterfly chart data
    butterfly_data = []
    for tenet in tenets:
        butterfly_data.append({
            'id': tenet['id'],
            'name': tenet['name'],
            'strength_count': tenet_strengths.get(tenet['id'], 0),
            'improvement_count': tenet_improvements.get(tenet['id'], 0)
        })

    # Sort by net score
    butterfly_data.sort(key=lambda x: (x['strength_count'] - x['improvement_count']), reverse=True)

    # Generate butterfly chart image
    chart_image = generate_butterfly_chart_image(
        butterfly_data,
        manager_selected_strengths,
        manager_selected_improvements
    )

    # Organize feedback comments
    strengths_comments = [fb.strengths_text for fb in feedbacks if fb.strengths_text]
    improvements_comments = [fb.improvements_text for fb in feedbacks if fb.improvements_text]

    session.close()

    # Render PDF template
    html_content = render_template(
        'report_pdf.html',
        team_member=team_member.to_dict(),
        manager=manager.to_dict() if manager else {'name': manager_uid},
        feedback_count=len(feedbacks),
        chart_image=chart_image,
        strengths_comments=strengths_comments,
        improvements_comments=improvements_comments,
        manager_feedback_text=(manager_feedback.feedback_text if manager_feedback else ''),
        generation_date=datetime.now().strftime('%B %d, %Y at %I:%M %p')
    )

    # Convert to PDF
    pdf_buffer = io.BytesIO()
    HTML(string=html_content).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)

    # Return PDF file
    filename = f"Feedback_Report_{team_member.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


if __name__ == '__main__':
    # Disable template caching for development
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    app.run(debug=True, port=5001)
