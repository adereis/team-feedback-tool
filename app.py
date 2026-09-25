"""
Team Feedback Tool - Flask Application

Routes:
- / : Home page (mode-aware navigation)
- /feedback : Stateless feedback form (for hosted/Workday workflow)
- /individual : Individual feedback collection (for local workflow)
- /manager : Manager feedback dashboard
- /manager/import-xlsx : Import feedback from Workday XLSX
- /manager/report/<user_id> : View/edit report for team member
- /manager/export-pdf/<user_id> : Export PDF report
- /demo : Demo landing page; /demo/... serves the shared routes on a sandbox DB

Routes shared by local and demo mode live on the `views` blueprint, which is
registered twice (at / and at /demo). They reach the database and the session
through get_db() and session_key(), which resolve per request.
"""

from flask import (
    Blueprint, Flask, g, render_template, request, jsonify, send_file, redirect, url_for,
    session as flask_session
)
from models import create_db_engine, Person, Feedback, ManagerFeedback, WorkdayFeedback, name_to_user_id
from scripts.import_workday import import_workday_xlsx, get_available_date_ranges
from reports import load_member_feedback, orgchart_team_tally, workday_team_tally
from demo_mode import (
    get_demo_db, get_session_id, reset_session_data, demo_response_wrapper,
    start_cleanup_thread
)
import json
import csv
import io
import os
import base64
import secrets
import tempfile
import threading
from collections import defaultdict
from functools import wraps
from sqlalchemy import func
from sqlalchemy.orm import Session
# WeasyPrint imported lazily in PDF export functions (requires system libraries)
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Mode detection: HOSTED_MODE=true for ephemeral online deployment
HOSTED_MODE = os.environ.get('HOSTED_MODE', '').lower() == 'true'

app = Flask(__name__, template_folder='templates')


def load_secret_key(instance_path, hosted, environ=os.environ):
    """Key that signs Flask session cookies.

    SECRET_KEY from the environment wins. Hosted mode requires it: every
    worker and replica must share one key, and a key shipped in the source or
    the image would let anyone forge sessions. Locally, a random key is
    created once in the instance folder and reused, so the chosen identity
    survives restarts.
    """
    key = environ.get('SECRET_KEY')
    if key:
        return key
    if hosted:
        raise RuntimeError(
            "SECRET_KEY must be set when HOSTED_MODE=true, e.g. "
            "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')")

    path = os.path.join(instance_path, 'secret_key')
    if not os.path.exists(path):
        os.makedirs(instance_path, exist_ok=True)
        # Publish atomically: write a private temp file, then hard-link it into
        # place. If another process got there first, os.link fails and its key wins.
        fd, tmp = tempfile.mkstemp(dir=instance_path)
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_hex(32))
            try:
                os.link(tmp, path)
            except FileExistsError:
                pass
        finally:
            os.unlink(tmp)
    with open(path) as f:
        key = f.read().strip()
    if not key:
        raise RuntimeError(f"{path} is empty; delete it to generate a new key")
    return key


app.secret_key = load_secret_key(app.instance_path, HOSTED_MODE)
app.config['DATABASE'] = 'feedback.db'  # local mode DB; tests point this elsewhere

_engine_lock = threading.Lock()


# Demo mode lives under this prefix; the shared routes are served again there
DEMO_PREFIX = '/demo'


def is_demo_request():
    """Check if current request is a demo mode request."""
    return request.path == DEMO_PREFIX or request.path.startswith(DEMO_PREFIX + '/')


def db_engine():
    """Engine for the local DB, created once per process on first use.

    Creating it per request (as init_db() does for scripts) would rebuild the
    connection pool and re-run schema creation on every call.
    """
    with _engine_lock:
        if 'feedback_db' not in app.extensions:
            app.extensions['feedback_db'] = create_db_engine(app.config['DATABASE'])
        return app.extensions['feedback_db']


def dispose_db_engine():
    """Drop the local DB engine so the next request opens app.config['DATABASE'] afresh."""
    with _engine_lock:
        engine = app.extensions.pop('feedback_db', None)
    if engine is not None:
        engine.dispose()


def get_db():
    """Database session for this request: the visitor's sandbox under /demo, else the local DB.

    One session per request, closed by close_db() even when the route raises,
    so routes never close it themselves.
    """
    if 'db' not in g:
        g.db = get_demo_db() if is_demo_request() else Session(db_engine())
    return g.db


@app.teardown_appcontext
def close_db(exc):
    """Close the request's DB session (rolling back anything uncommitted)."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def session_key(name):
    """Flask session key for this request; demo identities never mix with local ones."""
    return f'demo_{name}' if is_demo_request() else name


@app.after_request
def attach_demo_cookie(response):
    """Give every /demo response the visitor's sandbox cookie."""
    return demo_response_wrapper(response) if is_demo_request() else response


def local_only(f):
    """Decorator to block routes in hosted mode (only accessible locally).

    Demo requests pass through: they only touch the visitor's own sandbox.
    API routes get a JSON error so fetch() callers can parse it.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if HOSTED_MODE and not is_demo_request():
            message = "This feature is only available when running locally."
            if request.path.startswith('/api/'):
                return jsonify({"success": False, "error": message}), 403
            return render_template('error.html',
                error_title="Not Available",
                error_message=message,
                show_demo_link=True
            ), 403
        return f(*args, **kwargs)
    return decorated_function


def error_page(status, title, message, action_url=None, action_label=None):
    """Render a styled error page with a way back, never a bare text response.

    Without an action the page links to the current mode's home page.
    """
    return render_template('error.html', error_title=title, error_message=message,
                           action_url=action_url, action_label=action_label), status


def is_api_request():
    """True for /api/... and /demo/api/..., whose callers expect JSON."""
    path = request.path
    if is_demo_request():
        path = path[len(DEMO_PREFIX):]
    return path.startswith('/api/')


@app.errorhandler(404)
def not_found(error):
    """Unknown URLs: JSON for API callers, the styled error page for people."""
    if is_api_request():
        return jsonify({"success": False, "error": "Not found"}), 404
    return error_page(404, "Page Not Found",
                      "There is no page at this address. It may have moved, or the link may be mistyped.")


@app.context_processor
def inject_mode_flags():
    """Make mode flags available to all templates"""
    demo = is_demo_request()
    return dict(
        hosted_mode=HOSTED_MODE,
        demo_mode=demo,
        # Shared routes for this mode: url_for(views ~ '.endpoint') in Jinja,
        # VIEWS_ROOT (from views_root) for URLs built in JavaScript
        views='demo' if demo else 'local',
        views_root=request.script_root + (DEMO_PREFIX if demo else ''),
        # Home page for this mode: url_for(home_endpoint)
        home_endpoint='demo_index' if demo else 'index',
    )


# Routes served both at / (local DB) and at /demo (visitor's sandbox);
# registered at the bottom of this module, once all routes are defined.
views = Blueprint('views', __name__)


# Load tenets configuration
# Prefer tenets.json (org-specific), fall back to samples/tenets-sample.json
TENETS_FILE = 'tenets.json' if os.path.exists('tenets.json') else 'samples/tenets-sample.json'


def load_tenets():
    """Load tenets from JSON file (tenets.json if exists, else samples/tenets-sample.json)"""
    with open(TENETS_FILE, 'r') as f:
        data = json.load(f)
    return [t for t in data['tenets'] if t.get('active', True)]


def tenet_selection_error(strengths, improvements):
    """Return why a tenet selection breaks the feedback rule, or None if valid.

    One rule for peer and manager feedback alike: exactly 3 strengths,
    2-3 improvements, and each tenet at most once (never as both a strength
    and an improvement). The pages enforce the same rule before saving.
    """
    if not (isinstance(strengths, list) and isinstance(improvements, list)
            and all(isinstance(t, str) for t in strengths + improvements)):
        return "Tenet selections must be lists of tenet IDs"
    if len(strengths) != 3:
        return "Must select exactly 3 strengths"
    if not 2 <= len(improvements) <= 3:
        return "Must select 2-3 improvements"
    if len(set(strengths + improvements)) != len(strengths) + len(improvements):
        return "A tenet can be selected only once"
    return None


@app.route('/')
def index():
    """Home page - select mode"""
    session = get_db()
    total_people = session.query(Person).count()
    return render_template('index.html', has_data=total_people > 0)


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


@views.route('/api/db-stats')
@local_only
def get_db_stats():
    """Get database statistics for home page"""
    session = get_db()

    total_people = session.query(Person).count()
    managers = session.query(Person).filter(Person.direct_reports.any()).count()
    team_members = total_people - managers
    peer_feedback = session.query(Feedback).count()
    manager_reviews = session.query(ManagerFeedback).count()


    return jsonify({
        "success": True,
        "total_people": total_people,
        "managers": managers,
        "team_members": team_members,
        "peer_feedback": peer_feedback,
        "manager_reviews": manager_reviews
    })


@app.route('/api/import-orgchart', methods=['POST'])
@local_only
def import_orgchart_web():
    """Import orgchart CSV via web interface"""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    reset_db = request.form.get('reset', 'false').lower() == 'true'

    session = get_db()

    try:
        # Read CSV
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)

        # Validate required columns
        required_cols = ['Name', 'User ID', 'Job Title', 'Email', 'Manager UID']
        if reader.fieldnames is None:
            return jsonify({"success": False, "error": "Empty or invalid CSV file"}), 400

        missing_cols = [col for col in required_cols if col not in reader.fieldnames]
        if missing_cols:
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

        return jsonify({
            "success": True,
            "new_count": count,
            "updated_count": updated,
            "reset": reset_db
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@views.route('/individual')
@local_only
def individual_feedback():
    """Individual feedback collection page"""
    current_user_id = flask_session.get(session_key('user_id'))

    # If no user selected, show selection page
    if not current_user_id:
        session = get_db()
        all_people = session.query(Person).order_by(Person.name).all()
        return render_template('individual_select.html', all_people=[p.to_dict() for p in all_people])

    # User selected - show feedback page
    session = get_db()
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

    return render_template(
        'individual_feedback.html',
        current_user=current_user,
        all_people=[p.to_dict() for p in all_people],
        people_by_manager=people_by_manager,
        existing_feedback=[f.to_dict() for f in existing_feedback],
        tenets=tenets
    )


@views.route('/individual/<user_id>')
@local_only
def individual_login(user_id):
    """Direct individual login via URL - sets session and redirects to feedback page"""
    # Allow any user_id (even if not in database) for external providers
    flask_session[session_key('user_id')] = user_id
    return redirect(url_for('.individual_feedback'))


@views.route('/individual/switch')
@local_only
def individual_switch():
    """Clear user session and return to selection"""
    flask_session.pop(session_key('user_id'), None)
    return redirect(url_for('.individual_feedback'))


@views.route('/api/set-user', methods=['POST'])
@local_only
def set_user():
    """Set current user in session - allows custom user IDs not in database"""
    data = request.get_json()
    user_id = data.get('user_id')

    if not user_id:
        return jsonify({"success": False, "error": "Missing user_id"}), 400

    # Allow any user_id, even if not in database
    # This supports external feedback providers
    flask_session[session_key('user_id')] = user_id
    return jsonify({"success": True})


@views.route('/api/feedback', methods=['POST'])
@local_only
def save_feedback():
    """Save individual feedback"""
    data = request.get_json()

    from_user_id = flask_session.get(session_key('user_id'))
    if not from_user_id:
        return jsonify({"success": False, "error": "No user selected"}), 400

    to_user_id = data.get('to_user_id')
    strengths = data.get('strengths', [])
    improvements = data.get('improvements', [])
    strengths_text = data.get('strengths_text', '')
    improvements_text = data.get('improvements_text', '')

    if not to_user_id:
        return jsonify({"success": False, "error": "Missing to_user_id"}), 400

    error = tenet_selection_error(strengths, improvements)
    if error:
        return jsonify({"success": False, "error": error}), 400

    session = get_db()

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

    return jsonify({"success": True})


@views.route('/api/feedback/<to_user_id>', methods=['DELETE'])
@local_only
def delete_feedback(to_user_id):
    """Delete feedback for a specific person"""
    from_user_id = flask_session.get(session_key('user_id'))
    if not from_user_id:
        return jsonify({"success": False, "error": "No user selected"}), 400

    session = get_db()
    feedback = session.query(Feedback).filter_by(
        from_user_id=from_user_id,
        to_user_id=to_user_id
    ).first()

    if feedback:
        session.delete(feedback)
        session.commit()

    return jsonify({"success": True})


@views.route('/manager')
@local_only
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
        flask_session[session_key('manager_name')] = manager_name
        flask_session.pop(session_key('manager_uid'), None)  # Clear UID-based session
        return redirect(url_for('.manager_dashboard'))

    # Check session for manager identity
    manager_name = flask_session.get(session_key('manager_name'))
    manager_uid = flask_session.get(session_key('manager_uid'))

    # If no manager selected, show selection page
    if not manager_name and not manager_uid:
        session = get_db()
        # Get all managers from orgchart (if any)
        managers = session.query(Person).filter(Person.direct_reports.any()).order_by(Person.name).all()
        return render_template('manager_select.html', managers=[m.to_dict() for m in managers])

    session = get_db()
    team_members = []
    manager_info = {}
    has_orgchart = False

    if manager_uid:
        # UID-based workflow (from orgchart)
        manager = session.query(Person).filter_by(user_id=manager_uid).first()
        if not manager:
            flask_session.pop(session_key('manager_uid'), None)
            return redirect(url_for('.manager_dashboard'))

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


    return render_template(
        'manager_dashboard.html',
        manager=manager_info,
        team_members=team_members,
        has_orgchart=has_orgchart
    )


@views.route('/api/team-butterfly-data')
@local_only
def get_team_butterfly_data():
    """Get aggregated butterfly chart data for entire team.

    Supports two modes:
    1. UID-based (orgchart workflow): Uses manager_uid from session
    2. Name-based (Workday workflow): Uses manager_name from session
    """
    manager_uid = flask_session.get(session_key('manager_uid'))
    manager_name = flask_session.get(session_key('manager_name'))

    if not manager_uid and not manager_name:
        return jsonify({"success": False, "error": "No manager selected"}), 400

    session = get_db()

    if manager_uid:
        tally = orgchart_team_tally(session, manager_uid)
    else:
        tally = workday_team_tally(session, name_to_user_id(manager_name))

    butterfly_data = tally.butterfly(load_tenets())

    return jsonify({
        "success": True,
        "butterfly_data": butterfly_data
    })


@views.route('/manager/<manager_uid>')
@local_only
def manager_login(manager_uid):
    """Direct manager login via URL - sets session and redirects to dashboard"""
    session = get_db()
    manager = session.query(Person).filter_by(user_id=manager_uid).first()

    if not manager:
        return error_page(404, "Manager Not Found",
                          f"No one with the ID \"{manager_uid}\" is in the imported orgchart.",
                          url_for('.manager_dashboard'), "Choose a Manager")

    # Set manager in session
    flask_session[session_key('manager_uid')] = manager_uid

    # Redirect to dashboard
    return redirect(url_for('.manager_dashboard'))


@views.route('/manager/switch')
@local_only
def manager_switch():
    """Clear manager session and return to selection"""
    flask_session.pop(session_key('manager_uid'), None)
    flask_session.pop(session_key('manager_name'), None)
    return redirect(url_for('.manager_dashboard'))


@views.route('/api/set-manager', methods=['POST'])
@local_only
def set_manager():
    """Set current manager in session"""
    data = request.get_json()
    manager_uid = data.get('manager_uid')

    if not manager_uid:
        return jsonify({"success": False, "error": "Missing manager_uid"}), 400

    session = get_db()
    manager = session.query(Person).filter_by(user_id=manager_uid).first()

    if not manager:
        return jsonify({"success": False, "error": "Manager not found"}), 404

    flask_session[session_key('manager_uid')] = manager_uid
    return jsonify({"success": True})


@app.route('/manager/import-xlsx', methods=['POST'])
@local_only
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
        result = import_workday_xlsx(tmp_path, app.config['DATABASE'])
        return jsonify(result.to_dict())
    finally:
        # Clean up temp file
        os.unlink(tmp_path)


@views.route('/api/workday-feedback')
@local_only
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

    session = get_db()

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

    return jsonify({
        "success": True,
        "feedbacks": [fb.to_dict() for fb in feedbacks],
        "total": len(feedbacks)
    })


@views.route('/api/workday-feedback/recipients')
@local_only
def get_workday_recipients():
    """Get list of unique recipients with feedback counts"""
    session = get_db()

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


    return jsonify({
        "success": True,
        "recipients": recipients
    })


@views.route('/api/workday-feedback/date-ranges')
@local_only
def get_date_ranges():
    """Get available date ranges for filtering"""
    session = get_db()
    ranges = get_available_date_ranges(session)

    return jsonify({
        "success": True,
        "ranges": [
            {"year": r[0], "month": r[1], "count": r[2]}
            for r in ranges
        ]
    })


def no_manager_session_page():
    """Report and PDF URLs opened without a manager chosen (or after sign-out)."""
    return error_page(400, "Choose Your Team First",
                      "Reports open from the Manager Dashboard once you have chosen "
                      "your name. Your manager session may have ended.",
                      url_for('.manager_dashboard'), "Go to Manager Dashboard")


def team_member_not_found_page():
    return error_page(404, "Team Member Not Found",
                      "This person is not in the orgchart or the imported Workday feedback.",
                      url_for('.manager_dashboard'), "Back to Dashboard")


def not_in_team_page():
    return error_page(403, "Not on Your Team",
                      "This person does not report to the manager you are signed in as.",
                      url_for('.manager_dashboard'), "Back to Dashboard")


@views.route('/manager/report/<user_id>')
@views.route('/manager/report')
@local_only
def view_report(user_id=None):
    """View feedback report for team member.

    Supports multiple access modes:
    1. Real user_id: /manager/report/emp001 (orgchart-based)
    2. Derived user_id: /manager/report/wd_a1b2c3d4 (Workday-only)
    3. Name query param: /manager/report?name=Robin%20Rollback (legacy)
    """
    manager_uid = flask_session.get(session_key('manager_uid'))
    manager_name = flask_session.get(session_key('manager_name'))

    if not manager_uid and not manager_name:
        return no_manager_session_page()

    # Get team member name from query param if no user_id
    team_member_name = request.args.get('name', '').strip() if not user_id else None

    if not user_id and not team_member_name:
        return error_page(400, "No Team Member Chosen",
                          "Open a report from your team list on the Manager Dashboard.",
                          url_for('.manager_dashboard'), "Go to Manager Dashboard")

    session = get_db()

    # Initialize team member info
    team_member_info = None
    team_member_user_id = user_id

    # Check if this is a derived ID (starts with 'wd_')
    is_derived_id = user_id and user_id.startswith('wd_')

    if user_id and not is_derived_id:
        # Real user_id from orgchart
        team_member = session.query(Person).filter_by(user_id=user_id).first()
        if not team_member:
            return team_member_not_found_page()

        # Verify team membership if using orgchart workflow
        if manager_uid and team_member.manager_uid != manager_uid:
            return not_in_team_page()

        team_member_info = team_member.to_dict()
        team_member_name = team_member.name

    elif user_id and is_derived_id:
        # Derived ID from Workday - find the name from Workday feedback
        # Look for a recipient whose derived ID matches
        # FIXME: reverse lookup by re-hashing every recipient name; part of the
        # name-based identity issue (see models.name_to_user_id)
        wd_recipient = session.query(WorkdayFeedback.about).distinct().all()
        for (name,) in wd_recipient:
            if name_to_user_id(name) == user_id:
                team_member_name = name
                break

        if not team_member_name:
            return team_member_not_found_page()

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

    # Use manager_uid or derived ID from manager_name
    effective_manager_uid = manager_uid or name_to_user_id(manager_name)
    member = load_member_feedback(session, team_member_user_id, team_member_name, effective_manager_uid)

    tenets = load_tenets()
    butterfly_data = member.manager_view().butterfly(tenets)

    # Prepare legacy feedback with giver names for manager view (non-anonymous)
    feedbacks_with_names = []
    for fb in member.peer:
        fb_dict = fb.to_dict()
        # Get giver's name
        giver = session.query(Person).filter_by(user_id=fb.from_user_id).first()
        fb_dict['from_name'] = giver.name if giver else fb.from_user_id
        fb_dict['source'] = 'legacy'
        feedbacks_with_names.append(fb_dict)

    # Add structured Workday feedback
    for fb in member.workday_structured:
        fb_dict = fb.to_dict()
        fb_dict['from_name'] = fb.from_name
        fb_dict['source'] = 'workday_structured'
        feedbacks_with_names.append(fb_dict)

    return render_template(
        'report.html',
        team_member=team_member_info,
        feedbacks=feedbacks_with_names,
        generic_feedbacks=[fb.to_dict() for fb in member.workday_generic],
        butterfly_data=butterfly_data,
        manager_feedback=member.manager.to_dict() if member.manager else None,
        tenets=tenets
    )


@views.route('/api/manager-feedback', methods=['POST'])
@local_only
def save_manager_feedback():
    """Save manager's own feedback.

    Supports both orgchart-based (manager_uid from session) and
    Workday-based (derived ID from manager_name) workflows.
    """
    data = request.get_json()

    manager_uid = flask_session.get(session_key('manager_uid'))
    manager_name = flask_session.get(session_key('manager_name'))

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

    error = tenet_selection_error(selected_strengths, selected_improvements)
    if error:
        return jsonify({"success": False, "error": error}), 400

    session = get_db()

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


@views.route('/manager/export-pdf/<user_id>')
@local_only
def export_pdf_report(user_id):
    """Export feedback report as PDF.

    The PDF is the employee's view, unlike the report page (the manager's
    view): it covers peer feedback given in this tool plus the manager's picks
    and text, and deliberately leaves out Workday feedback, some of which the
    employee may not be allowed to see.

    Works for both manager workflows: orgchart (manager_uid) and Workday
    (manager_name, via its derived ID), like view_report.
    """
    manager_uid = flask_session.get(session_key('manager_uid'))
    manager_name = flask_session.get(session_key('manager_name'))
    if not manager_uid and not manager_name:
        return no_manager_session_page()

    effective_manager_uid = manager_uid or name_to_user_id(manager_name)

    session = get_db()

    # Get team member
    team_member = session.query(Person).filter_by(user_id=user_id).first()
    if not team_member:
        return team_member_not_found_page()

    # Verify team membership if using orgchart workflow
    if manager_uid and team_member.manager_uid != manager_uid:
        return not_in_team_page()

    # Get manager info
    manager = session.query(Person).filter_by(user_id=effective_manager_uid).first()

    member = load_member_feedback(session, user_id, team_member.name, effective_manager_uid)
    manager_feedback = member.manager
    manager_selected_strengths = manager_feedback.get_selected_strengths() if manager_feedback else []
    manager_selected_improvements = manager_feedback.get_selected_improvements() if manager_feedback else []

    # Employee view: no Workday feedback (see docstring)
    butterfly_data = member.employee_view().butterfly(load_tenets())

    # Generate butterfly chart image
    chart_image = generate_butterfly_chart_image(
        butterfly_data,
        manager_selected_strengths,
        manager_selected_improvements
    )

    # Peer comments given in this tool, anonymous in the PDF
    strengths_comments = [fb.strengths_text for fb in member.peer if fb.strengths_text]
    improvements_comments = [fb.improvements_text for fb in member.peer if fb.improvements_text]

    # Render PDF template
    html_content = render_template(
        'report_pdf.html',
        team_member=team_member.to_dict(),
        manager=manager.to_dict() if manager else {'name': manager_name or effective_manager_uid},
        feedback_count=len(member.peer),
        chart_image=chart_image,
        strengths_comments=strengths_comments,
        improvements_comments=improvements_comments,
        manager_feedback_text=(manager_feedback.feedback_text if manager_feedback else ''),
        generation_date=datetime.now().strftime('%B %d, %Y at %I:%M %p')
    )

    # Convert to PDF (lazy import - requires system libraries)
    from weasyprint import HTML
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


# =============================================================================
# DEMO-ONLY ROUTES
# Everything else under /demo comes from the `views` blueprint (see bottom).
# =============================================================================

@app.route(DEMO_PREFIX)
def demo_index():
    """Demo mode landing page"""
    db = get_db()
    stats = {
        'total_people': db.query(Person).count(),
        'peer_feedback': db.query(Feedback).count(),
        'manager_reviews': db.query(ManagerFeedback).count()
    }

    return render_template('demo_index.html', stats=stats)


@app.route(f'{DEMO_PREFIX}/api/load-sample-workday', methods=['POST'])
def demo_load_sample_workday():
    """Demo mode: Load/reload sample Workday feedback data"""
    db = get_db()

    # Check if Workday feedback already exists
    existing_count = db.query(WorkdayFeedback).count()

    if existing_count > 0:
        # Data already loaded
        return jsonify({
            "success": True,
            "imported": existing_count,
            "message": "Sample data already loaded"
        })

    # No data - the template should have it, but if not, report it
    return jsonify({
        "success": True,
        "imported": 0,
        "message": "No sample data available. Try resetting your demo session."
    })


@app.route(f'{DEMO_PREFIX}/api/reset', methods=['POST'])
def demo_reset():
    """Demo mode: Reset session data to fresh template (the banner's reset button)"""
    if not reset_session_data(get_session_id()):
        return jsonify({"success": False, "error": "Could not restore the sample data"}), 500

    # The sample data replaced the sandbox, so forget who the visitor signed in as
    for key in ('user_id', 'manager_uid', 'manager_name'):
        flask_session.pop(session_key(key), None)

    return jsonify({"success": True})


# Start cleanup thread when running with gunicorn or similar
# (Only starts if server is configured for demo sessions)
_cleanup_started = False

@app.before_request
def ensure_demo_cleanup_started():
    """Start demo cleanup thread on first request (if not already started)"""
    global _cleanup_started
    if not _cleanup_started and is_demo_request():
        start_cleanup_thread()
        _cleanup_started = True


# Register the shared routes once per mode. `name` gives each registration its
# own endpoint namespace: url_for('local.view_report') vs url_for('demo.view_report').
app.register_blueprint(views, name='local')
app.register_blueprint(views, url_prefix=DEMO_PREFIX, name='demo')


if __name__ == '__main__':
    # Disable template caching for development
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    app.run(debug=True, port=5001)
