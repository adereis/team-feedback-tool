"""
Tests for the report tallies (reports.py).

Fixture data (conftest.test_db): emp001 and emp002 report to mgr001 and
reviewed each other; mgr001 picked tenet1, tenet2 / tenet3 for emp001.
"""

import json
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import ManagerFeedback, WorkdayFeedback
from reports import Tally, load_member_feedback, orgchart_team_tally, workday_team_tally

TENETS = [{'id': f'tenet{i}', 'name': f'Tenet {i}'} for i in range(1, 6)]


def add_workday(db, about, strengths=None, improvements=None):
    """Add a structured Workday entry, or a generic one when no tenets are given."""
    entry = WorkdayFeedback(about=about, from_name='Workday Giver', question=f'Q{db.query(WorkdayFeedback).count()}',
                            feedback='text', date=datetime(2025, 11, 1))
    if strengths is not None:
        entry.is_structured = 1
        entry.strengths = json.dumps(strengths)
        entry.improvements = json.dumps(improvements)
    db.add(entry)
    db.commit()


def counts(tally, tenet):
    return tally.strengths[tenet], tally.improvements[tenet]


class TestMemberViews:
    """The manager view counts Workday feedback; the employee view does not."""

    @pytest.fixture
    def member(self, db_session):
        add_workday(db_session, 'Charlie Developer', ['tenet5', 'tenet4', 'tenet3'], ['tenet1', 'tenet2'])
        add_workday(db_session, 'Charlie Developer')  # generic: never counted
        return load_member_feedback(db_session, 'emp001', 'Charlie Developer', 'mgr001')

    def test_member_feedback_grouped_by_source(self, member):
        """Test that each source is loaded for the member"""
        assert len(member.peer) == 1
        assert len(member.workday_structured) == 1
        assert len(member.workday_generic) == 1
        assert member.manager is not None

    def test_manager_view_counts_all_sources(self, member):
        """Test peer (tenet2 strength), Workday (tenet2 improvement) and manager picks"""
        tally = member.manager_view()

        # tenet2: strength from peer emp002 + manager pick; improvement from peer + Workday
        assert counts(tally, 'tenet2') == (2, 2)
        assert counts(tally, 'tenet5') == (1, 0)  # only Workday picked tenet5

    def test_employee_view_leaves_out_workday(self, member):
        """Test the PDF tally is peer feedback plus manager picks only"""
        tally = member.employee_view()

        assert tally.strengths['tenet5'] == 0
        assert counts(tally, 'tenet2') == (2, 1)

    def test_derived_id_has_no_peer_feedback(self, db_session):
        """Test a Workday-only person (wd_ ID) never matches in-tool feedback"""
        member = load_member_feedback(db_session, 'wd_12345678', 'Nobody', 'mgr001')

        assert member.peer == []
        assert member.manager is None


class TestTally:
    """Chart rows built from a tally."""

    def test_butterfly_sorted_by_net_score(self):
        """Test rows run from most net-positive to most net-negative"""
        tally = Tally()
        tally.add(['tenet3', 'tenet3', 'tenet1'], ['tenet2'])

        rows = tally.butterfly(TENETS)

        assert [r['id'] for r in rows] == ['tenet3', 'tenet1', 'tenet4', 'tenet5', 'tenet2']
        assert rows[0] == {'id': 'tenet3', 'name': 'Tenet 3', 'strength_count': 2, 'improvement_count': 0}

    def test_butterfly_ties_keep_tenet_order(self):
        """Test tenets with equal net scores stay in configuration order"""
        rows = Tally().butterfly(TENETS)

        assert [r['id'] for r in rows] == [t['id'] for t in TENETS]


class TestTeamTallies:
    """Team charts for both manager workflows."""

    def test_orgchart_team_is_sum_of_member_views(self, db_session):
        """Test the team chart agrees with the report pages it summarizes"""
        add_workday(db_session, 'Diana Developer', ['tenet5', 'tenet4', 'tenet3'], ['tenet1', 'tenet2'])
        expected = Tally()
        for user_id, name in [('emp001', 'Charlie Developer'), ('emp002', 'Diana Developer')]:
            expected.add_tally(load_member_feedback(db_session, user_id, name, 'mgr001').manager_view())

        team = orgchart_team_tally(db_session, 'mgr001')

        assert team.strengths == expected.strengths
        assert team.improvements == expected.improvements

    def test_orgchart_team_ignores_picks_for_former_reports(self, db_session):
        """Test manager picks for someone no longer on the team are not counted"""
        stale = ManagerFeedback(manager_uid='mgr001', team_member_uid='emp003')  # emp003 reports to mgr002
        stale.set_selected_strengths(['tenet5', 'tenet4', 'tenet3'])
        stale.set_selected_improvements(['tenet1', 'tenet2'])
        db_session.add(stale)
        db_session.commit()

        team = orgchart_team_tally(db_session, 'mgr001')

        assert team.strengths['tenet5'] == 0

    def test_workday_team_counts_only_structured_workday(self, db_session):
        """Test the by-name team chart ignores in-tool feedback and manager picks"""
        add_workday(db_session, 'Anyone', ['tenet5', 'tenet4', 'tenet3'], ['tenet1', 'tenet2'])
        add_workday(db_session, 'Anyone')

        team = workday_team_tally(db_session)

        assert sum(team.strengths.values()) == 3
        assert sum(team.improvements.values()) == 2
