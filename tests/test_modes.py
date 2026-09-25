"""
Tests for hosted mode and demo mode request handling.

Tests cover:
- Hosted mode blocks the local-only JSON API but keeps the stateless form
- Demo requests are served from the visitor's sandbox, even in hosted mode
- Demo session cookies are validated before being used in file paths
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
from models import WorkdayFeedback


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
