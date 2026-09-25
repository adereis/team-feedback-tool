"""
Tests for what the exported PDF report says, read back from the PDF text.

Tests cover:
- Typed feedback keeps its paragraphs and line breaks
"""

import io
import os
import sys

import pytest
from pypdf import PdfReader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Feedback, ManagerFeedback


def pdf_lines(response):
    """Return the PDF's text as a list of non-blank, stripped lines."""
    assert response.status_code == 200
    assert response.content_type == 'application/pdf'
    reader = PdfReader(io.BytesIO(response.data))
    text = '\n'.join(page.extract_text() for page in reader.pages)
    return [line.strip() for line in text.splitlines() if line.strip()]


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
