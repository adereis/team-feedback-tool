"""
Tests for demo mode request handling.

Tests cover:
- Demo requests are served from the visitor's sandbox
"""

import json
import os
import sys
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import demo_mode
from models import WorkdayFeedback


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
