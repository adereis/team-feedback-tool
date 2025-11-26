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
from feedback_models import init_db, Person, Feedback, ManagerFeedback
import json
import csv
import io
import os
from collections import defaultdict
from sqlalchemy import func

app = Flask(__name__, template_folder='feedback_templates')
app.secret_key = 'feedback-tool-secret-key-change-in-production'

# Load tenets configuration
# Prefer tenets.json (org-specific), fall back to tenets-sample.json
TENETS_FILE = 'tenets.json' if os.path.exists('tenets.json') else 'tenets-sample.json'


def load_tenets():
    """Load tenets from JSON file (tenets.json if exists, else tenets-sample.json)"""
    with open(TENETS_FILE, 'r') as f:
        data = json.load(f)
    return [t for t in data['tenets'] if t.get('active', True)]


@app.route('/')
def index():
    """Home page - select mode"""
    return render_template('index.html')


@app.route('/individual')
def individual_feedback():
    """Individual feedback collection page"""
    session = init_db()

    # Get current user from session (or set default for testing)
    current_user_id = flask_session.get('user_id')
    current_user = None

    if current_user_id:
        current_user = session.query(Person).filter_by(user_id=current_user_id).first()
        # If not in database, create a mock user object
        if not current_user:
            current_user = type('obj', (object,), {
                'user_id': current_user_id,
                'name': current_user_id,
                'email': '',
                'job_title': 'External'
            })

    # Get all people (for selection)
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
            feedback_by_manager[receiver.manager_uid].append(feedback)

    # Build list of managers with feedback counts
    export_list = []
    for manager_uid, feedback_list in feedback_by_manager.items():
        manager = session.query(Person).filter_by(user_id=manager_uid).first()
        export_list.append({
            'manager_uid': manager_uid,
            'manager_name': manager.name if manager else manager_uid,
            'feedback_count': len(feedback_list)
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
    """Manager dashboard - view team and feedback"""
    manager_uid = flask_session.get('manager_uid')

    # If no manager selected, show selection page
    if not manager_uid:
        session = init_db()
        # Get all managers (people who have direct reports)
        managers = session.query(Person).filter(Person.direct_reports.any()).order_by(Person.name).all()
        session.close()
        return render_template('manager_select.html', managers=[m.to_dict() for m in managers])

    # Manager selected - show dashboard
    manager = None
    team_members = []

    session = init_db()
    manager = session.query(Person).filter_by(user_id=manager_uid).first()

    if not manager:
        # Invalid manager_uid in session - clear it
        flask_session.pop('manager_uid', None)
        session.close()
        return redirect('/manager')

    team_members_objs = session.query(Person).filter_by(manager_uid=manager_uid).all()

    # Convert to dicts and add feedback count
    for tm in team_members_objs:
        tm_dict = tm.to_dict()
        tm_dict['feedback_count'] = session.query(Feedback).filter_by(to_user_id=tm.user_id).count()
        team_members.append(tm_dict)

    session.close()

    return render_template(
        'manager_dashboard.html',
        manager=manager.to_dict(),
        team_members=team_members
    )


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

    # Read CSV
    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    reader = csv.DictReader(stream)

    count = 0
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

        if not existing:
            feedback = Feedback(
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                strengths_text=row['Strengths Text'],
                improvements_text=row['Improvements Text']
            )
            feedback.set_strengths(strengths)
            feedback.set_improvements(improvements)
            session.add(feedback)
            count += 1

    session.commit()
    session.close()

    return jsonify({"success": True, "count": count})


@app.route('/manager/report/<user_id>')
def view_report(user_id):
    """View feedback report for team member"""
    manager_uid = flask_session.get('manager_uid')
    if not manager_uid:
        return "Please select your manager ID first", 400

    session = init_db()

    # Get team member
    team_member = session.query(Person).filter_by(user_id=user_id).first()
    if not team_member or team_member.manager_uid != manager_uid:
        session.close()
        return "Team member not found or not in your team", 403

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

    session.close()

    return render_template(
        'report.html',
        team_member=team_member.to_dict(),
        feedbacks=[f.to_dict() for f in feedbacks],
        butterfly_data=butterfly_data,
        manager_feedback=manager_feedback.to_dict() if manager_feedback else None,
        tenets=tenets
    )


@app.route('/api/manager-feedback', methods=['POST'])
def save_manager_feedback():
    """Save manager's own feedback"""
    data = request.get_json()

    manager_uid = flask_session.get('manager_uid')
    if not manager_uid:
        return jsonify({"success": False, "error": "No manager selected"}), 400

    team_member_uid = data.get('team_member_uid')
    selected_strengths = data.get('selected_strengths', [])
    selected_improvements = data.get('selected_improvements', [])
    feedback_text = data.get('feedback_text', '')

    if not team_member_uid:
        return jsonify({"success": False, "error": "Missing team_member_uid"}), 400

    session = init_db()

    # Check if exists
    mgr_feedback = session.query(ManagerFeedback).filter_by(
        manager_uid=manager_uid,
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
            manager_uid=manager_uid,
            team_member_uid=team_member_uid,
            feedback_text=feedback_text
        )
        mgr_feedback.set_selected_strengths(selected_strengths)
        mgr_feedback.set_selected_improvements(selected_improvements)
        session.add(mgr_feedback)

    session.commit()
    session.close()

    return jsonify({"success": True})


if __name__ == '__main__':
    # Disable template caching for development
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    app.run(debug=True, port=5001)
