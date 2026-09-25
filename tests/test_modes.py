"""
Tests for hosted mode and demo mode request handling.

Tests cover:
- Hosted mode blocks the local-only JSON API but keeps the stateless form
- Demo requests are served from the visitor's sandbox, even in hosted mode
- Demo session cookies are validated before being used in file paths
- Shared routes keep demo identity, redirects and links under /demo
"""

import json
import os
import sys
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import demo_mode
from models import Person, WorkdayFeedback


@pytest.fixture
def hosted(monkeypatch):
    """Run the app as the public hosted deployment."""
    monkeypatch.setattr('app.HOSTED_MODE', True)


@pytest.fixture
def demo_db(tmp_path, monkeypatch):
    """Stand in for the visitor's sandbox with a DB holding one Workday entry."""
    db_path = tmp_path / 'demo.db'
    engine = create_engine(f'sqlite:///{db_path}')
    from models import Base
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    session = Session()
    session.add(Person(user_id='sbxmgr', name='Sandbox Manager', job_title='Manager'))
    session.add(Person(user_id='sbx001', name='Sandbox Person', job_title='Engineer',
                       manager_uid='sbxmgr'))
    session.add(WorkdayFeedback(
        about='Sandbox Person', from_name='Sandbox Giver',
        feedback='Nice work', date=datetime(2025, 11, 15)
    ))
    session.commit()
    session.close()

    monkeypatch.setattr('app.get_demo_db', Session)


class TestHostedMode:
    """Tests for HOSTED_MODE route guards."""

    @pytest.mark.parametrize('method,path', [
        ('get', '/api/db-stats'),
        ('post', '/api/feedback'),
        ('post', '/api/manager-feedback'),
        ('post', '/api/import-orgchart'),
        ('get', '/api/workday-feedback/recipients'),
    ])
    def test_hosted_api_request_returns_json_403(self, client, hosted, method, path):
        """Test that the local DB API is unreachable on the public deployment."""
        response = getattr(client, method)(path, json={})

        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['success'] is False

    def test_hosted_feedback_form_still_served(self, client, hosted):
        """Test that the stateless feedback form keeps working when hosted."""
        response = client.get('/feedback?for=Robin%20Rollback')

        assert response.status_code == 200

    def test_hosted_demo_api_request_allowed(self, client, hosted, demo_db):
        """Test that demo endpoints stay available when hosted."""
        response = client.get('/demo/api/workday-feedback/recipients')

        assert response.status_code == 200


class TestDemoWorkdayApi:
    """Tests for Workday read endpoints served under /demo."""

    def test_demo_recipients_reads_sandbox_db(self, client, demo_db):
        """Test that /demo reads the visitor's sandbox, not the local DB."""
        response = client.get('/demo/api/workday-feedback/recipients')

        data = json.loads(response.data)
        assert [r['name'] for r in data['recipients']] == ['Sandbox Person']

    def test_demo_date_ranges_reads_sandbox_db(self, client, demo_db):
        """Test that the date-range summary also comes from the sandbox."""
        response = client.get('/demo/api/workday-feedback/date-ranges')

        data = json.loads(response.data)
        assert data['ranges'] == [{'year': 2025, 'month': 11, 'count': 1}]

    def test_demo_response_sets_session_cookie(self, client, demo_db):
        """Test that a first demo request receives its sandbox cookie."""
        response = client.get('/demo/api/workday-feedback')

        assert demo_mode.SESSION_COOKIE_NAME in response.headers.get('Set-Cookie', '')


class TestDemoSessionId:
    """Tests for demo session cookie validation."""

    def test_session_id_valid_uuid_cookie_kept(self, app):
        """Test that a well-formed session cookie is reused."""
        existing = str(uuid.uuid4())
        with app.test_request_context(
                '/demo', headers={'Cookie': f'{demo_mode.SESSION_COOKIE_NAME}={existing}'}):
            assert demo_mode.get_session_id() == existing

    @pytest.mark.parametrize('cookie', ['../../etc/passwd', 'abc', str(uuid.uuid4()).upper()])
    def test_session_id_invalid_cookie_replaced(self, app, cookie):
        """Test that a cookie which is not a canonical UUID never reaches the file system."""
        with app.test_request_context(
                '/demo', headers={'Cookie': f'{demo_mode.SESSION_COOKIE_NAME}={cookie}'}):
            session_id = demo_mode.get_session_id()

            assert session_id != cookie
            assert str(uuid.UUID(session_id)) == session_id

            response = demo_mode.demo_response_wrapper(app.response_class())
            assert session_id in response.headers['Set-Cookie']


class TestSharedRoutes:
    """Tests for routes served at both / and /demo from one definition."""

    def test_demo_page_lists_sandbox_people(self, client, demo_db):
        """Test that a shared page reads the sandbox under /demo."""
        response = client.get('/demo/individual')

        assert b'Sandbox Person' in response.data
        assert b'Charlie Developer' not in response.data  # local test DB

    def test_demo_login_uses_demo_session_key(self, client, demo_db):
        """Test that demo identity never lands in the local session keys."""
        client.get('/demo/individual/sbx001')

        with client.session_transaction() as sess:
            assert sess.get('demo_user_id') == 'sbx001'
            assert 'user_id' not in sess

    @pytest.mark.parametrize('path,target', [
        ('/demo/individual/sbx001', '/demo/individual'),
        ('/demo/manager/switch', '/demo/manager'),
        ('/individual/emp001', '/individual'),
        ('/manager/switch', '/manager'),
    ])
    def test_redirect_stays_in_current_mode(self, client, demo_db, path, target):
        """Test that redirects resolve against the blueprint that served the request."""
        response = client.get(path)

        assert response.status_code == 302
        assert response.headers['Location'] == target

    def test_demo_nav_links_point_to_demo(self, client, demo_db):
        """Test that the shared nav bar links to the demo copies of the pages."""
        response = client.get('/demo/individual')

        assert b'href="/demo/manager"' in response.data
        assert b'href="/manager"' not in response.data


    @pytest.mark.parametrize('prefix,session_key,manager,member', [
        ('', 'manager_uid', 'mgr001', 'emp001'),
        ('/demo', 'demo_manager_uid', 'sbxmgr', 'sbx001'),
    ])
    def test_rendered_links_use_current_mode(self, client, demo_db, prefix, session_key, manager, member):
        """Test page links and the JS URL root follow the mode that served the page"""
        with client.session_transaction() as sess:
            sess[session_key] = manager

        dashboard = client.get(f'{prefix}/manager').get_data(as_text=True)
        report = client.get(f'{prefix}/manager/report/{member}').get_data(as_text=True)

        assert f'href="{prefix}/manager/switch"' in dashboard
        assert f'href="{prefix}/manager/report/{member}"' in dashboard
        assert f'href="{prefix}/manager">' in report  # back to dashboard
        assert f'const VIEWS_ROOT = "{prefix}";' in report

    @pytest.mark.parametrize('path,is_demo', [
        ('/demo', True), ('/demo/manager', True), ('/demonstration', False), ('/manager', False),
    ])
    def test_is_demo_request_matches_prefix_exactly(self, app, path, is_demo):
        """Test only /demo and paths below it count as demo requests"""
        from app import is_demo_request

        with app.test_request_context(path):
            assert is_demo_request() is is_demo


class TestDemoReset:
    """Tests for the demo banner's reset button and endpoint."""

    @pytest.fixture
    def signed_in(self, client):
        with client.session_transaction() as sess:
            sess.update(demo_user_id='sbx001', demo_manager_uid='sbxmgr', user_id='emp001')
        return client

    def test_demo_reset_restores_sandbox_and_signs_out_of_demo(self, signed_in, monkeypatch):
        """Test reset replaces the sandbox and clears only the demo identity"""
        calls = []
        monkeypatch.setattr('app.reset_session_data', lambda sid: calls.append(sid) or True)

        response = signed_in.post('/demo/api/reset')

        assert response.status_code == 200 and response.get_json()['success'] is True
        assert len(calls) == 1
        with signed_in.session_transaction() as sess:
            assert 'demo_user_id' not in sess and 'demo_manager_uid' not in sess
            assert sess['user_id'] == 'emp001'  # local identity untouched

    def test_demo_reset_failure_reports_error_and_keeps_session(self, signed_in, monkeypatch):
        """Test a failed reset is an error the button can show, not a silent success"""
        monkeypatch.setattr('app.reset_session_data', lambda sid: False)

        response = signed_in.post('/demo/api/reset')

        assert response.status_code == 500
        assert response.get_json()['error']
        with signed_in.session_transaction() as sess:
            assert sess['demo_user_id'] == 'sbx001'

    def test_reset_button_only_in_demo(self, client, demo_db):
        """Test the banner offers reset on demo pages, never in local mode"""
        assert b'id="demoResetBtn"' in client.get('/demo/individual').data
        assert b'id="demoResetBtn"' not in client.get('/individual').data


class TestSecretKey:
    """Tests for how the session signing key is chosen."""

    def test_secret_key_from_environment_wins(self, tmp_path):
        """Test an explicit SECRET_KEY is used as is, in any mode"""
        from app import load_secret_key

        assert load_secret_key(str(tmp_path), hosted=True, environ={'SECRET_KEY': 'k'}) == 'k'
        assert not (tmp_path / 'secret_key').exists()

    def test_hosted_without_secret_key_refuses_to_start(self, tmp_path):
        """Test hosted mode never falls back to a per-machine or built-in key"""
        from app import load_secret_key

        with pytest.raises(RuntimeError, match='SECRET_KEY must be set'):
            load_secret_key(str(tmp_path), hosted=True, environ={})

    def test_local_key_created_once_and_reused(self, tmp_path):
        """Test local mode creates a private random key and keeps using it"""
        from app import load_secret_key

        instance = tmp_path / 'instance'
        first = load_secret_key(str(instance), hosted=False, environ={})
        second = load_secret_key(str(instance), hosted=False, environ={})

        assert first == second and len(first) == 64
        assert (instance / 'secret_key').stat().st_mode & 0o777 == 0o600
        assert sorted(p.name for p in instance.iterdir()) == ['secret_key']  # temp file removed

    def test_empty_key_file_is_an_error(self, tmp_path):
        """Test a truncated key file fails loudly instead of disabling sessions"""
        from app import load_secret_key

        (tmp_path / 'secret_key').write_text('')

        with pytest.raises(RuntimeError, match='is empty'):
            load_secret_key(str(tmp_path), hosted=False, environ={})


class TestPdfExportByName:
    """Tests for PDF export in the Workday (name-based) manager workflow."""

    def test_export_pdf_for_name_based_manager(self, client):
        """Test that a manager who signed in by name can export a report."""
        with client.session_transaction() as sess:
            sess['manager_name'] = 'Alice Manager'

        response = client.get('/manager/export-pdf/emp001')

        assert response.status_code == 200
        assert response.content_type == 'application/pdf'

    def test_export_pdf_unknown_member_returns_404(self, client):
        """Test that exporting someone who does not exist is a 404, not a 403."""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        response = client.get('/manager/export-pdf/nobody')

        assert response.status_code == 404
