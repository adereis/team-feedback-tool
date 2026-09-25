"""
Tests for what the exported PDF report says, read back from the PDF text.

The text comes from poppler's pdftotext in layout mode, which keeps side-by-
side columns and the page header and footer; the pure-Python extractors
merged columns and dropped the footer. Skipped without pdftotext
(poppler-utils), like the Node tests without node.

Tests cover:
- Typed feedback keeps its paragraphs and line breaks
- The manager's picks are named in words, before the peer comments
- Every page says whose report it is and which page it is
- Peer comments never carry the peer's name
"""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Feedback, ManagerFeedback

PDFTOTEXT = shutil.which('pdftotext')

pytestmark = pytest.mark.skipif(PDFTOTEXT is None, reason='pdftotext (poppler-utils) is not installed')


def pdf_text(response):
    """Return the PDF's text as laid out on the page."""
    assert response.status_code == 200
    assert response.content_type == 'application/pdf'
    return subprocess.run([PDFTOTEXT, '-layout', '-', '-'], input=response.data,
                          capture_output=True, check=True).stdout.decode()


def pdf_lines(response):
    """Return the PDF's non-blank lines, stripped."""
    return [line.strip() for line in pdf_text(response).splitlines() if line.strip()]


@pytest.fixture
def manager_client(client):
    with client.session_transaction() as sess:
        sess['manager_uid'] = 'mgr001'
    return client


class TestPdfText:
    """Tests for how typed text reaches the PDF."""

    def test_pdf_manager_text_keeps_line_breaks(self, manager_client, db_session):
        """Test each typed line stays its own line instead of running together"""
        feedback = db_session.query(ManagerFeedback).filter_by(team_member_uid='emp001').one()
        feedback.feedback_text = 'Delivery was strong.\n\nGrowth next:\n- mentoring\n- planning'
        db_session.commit()

        lines = pdf_lines(manager_client.get('/manager/export-pdf/emp001'))

        for line in ['Delivery was strong.', 'Growth next:', '- mentoring', '- planning']:
            assert line in lines

    def test_pdf_peer_comment_keeps_line_breaks(self, manager_client, db_session):
        """Test peer comments keep their line breaks too"""
        feedback = db_session.query(Feedback).filter_by(to_user_id='emp001').one()
        feedback.strengths_text = 'Owns incidents.\nWrites the follow-up.'
        db_session.commit()

        lines = pdf_lines(manager_client.get('/manager/export-pdf/emp001'))

        assert 'Owns incidents.' in lines
        assert 'Writes the follow-up.' in lines


class TestPdfLayout:
    """Tests for what the employee reads, and in what order."""

    def test_pdf_names_manager_picks_before_peer_comments(self, manager_client):
        """Test the picks are listed by tenet name, ahead of the chart and comments"""
        text = pdf_text(manager_client.get('/manager/export-pdf/emp001'))

        manager = text.index('From Your Manager, Alice Manager')
        peer = text.index('Peer Comments')
        for pick in ('★ Test Tenet 1', '★ Test Tenet 2', '★ Test Tenet 3'):
            assert manager < text.index(pick) < peer
        assert manager < text.index('Solid performer, ready for next level') < peer

    def test_pdf_pages_carry_name_and_number(self, manager_client):
        """Test the footer names the person and numbers the pages"""
        text = pdf_text(manager_client.get('/manager/export-pdf/emp001'))

        assert "For Charlie Developer's performance review only" in text
        assert 'Page 1 of 1' in text
        assert 'Confidential' in text

    def test_pdf_peer_comments_are_anonymous(self, manager_client):
        """Test the peer who wrote a comment is never named in the PDF"""
        text = ' '.join(pdf_lines(manager_client.get('/manager/export-pdf/emp001')))

        assert 'Excellent problem solving' in text  # Diana Developer's comment
        assert 'Diana' not in text

    def test_pdf_without_manager_feedback_says_so(self, manager_client, db_session):
        """Test a report with no manager input says so instead of an empty section"""
        db_session.query(ManagerFeedback).delete()
        db_session.commit()

        lines = pdf_lines(manager_client.get('/manager/export-pdf/emp001'))

        assert 'Your manager has not added feedback yet.' in lines
