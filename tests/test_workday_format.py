"""
Round trip for the copy-for-Workday text format.

static/workday_format.js produces the text people paste into Workday, and
WorkdayFeedback.parse_structured_feedback() reads it back from the Workday
export. These tests run the real JS under Node and parse its output, so the
producer and the parser cannot drift apart unnoticed. Skipped without Node.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from models import WorkdayFeedback

FORMAT_JS = os.path.join(ROOT, 'static', 'workday_format.js')
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node is not installed')

TENETS = [{'id': 'own', 'name': 'Ownership'}, {'id': 'craft', 'name': 'Craft'},
          {'id': 'clarity', 'name': 'Clarity'}, {'id': 'delegate', 'name': 'Delegation'},
          {'id': 'plan', 'name': 'Planning'}, {'id': 'teach', 'name': 'Teaching'}]


def render(kind, feedback):
    """Run WorkdayFormat.<kind>(TENETS, feedback) in Node and return the text."""
    script = (f'const format = require({json.dumps(FORMAT_JS)});'
              f'process.stdout.write(format.{kind}({json.dumps(TENETS)}, {json.dumps(feedback)}));')
    return subprocess.run([NODE, '-e', script], capture_output=True, text=True, check=True).stdout


def parse(text):
    """Import the text as a Workday export row would be."""
    entry = WorkdayFeedback(about='Pat Example', from_name='Sam Giver', feedback=text)
    assert entry.parse_structured_feedback() is True
    return entry


class TestPeerCopyFormat:
    """Peer feedback copied from /feedback or the individual page."""

    def test_peer_copy_round_trip_keeps_tenets_and_comments(self):
        """Test tenet IDs and both comments survive paste-and-import"""
        text = render('peer', {
            'strengths': ['own', 'craft', 'clarity'],
            'improvements': ['delegate', 'plan', 'teach'],
            'strengths_text': 'Drives incidents to closure.\nWrites great postmortems.',
            'improvements_text': 'Could hand off more work.',
        })

        entry = parse(text)

        assert entry.get_strengths() == ['own', 'craft', 'clarity']
        assert entry.get_improvements() == ['delegate', 'plan', 'teach']
        assert entry.strengths_text == 'Drives incidents to closure.\nWrites great postmortems.'
        assert entry.improvements_text == 'Could hand off more work.'

    def test_peer_copy_without_comments_imports_no_text(self):
        """Test the tenet name bullets are not mistaken for comments"""
        entry = parse(render('peer', {
            'strengths': ['own', 'craft', 'clarity'],
            'improvements': ['delegate', 'plan'],
            'strengths_text': '',
            'improvements_text': '   ',
        }))

        assert entry.strengths_text is None
        assert entry.improvements_text is None

    def test_peer_copy_prints_tenet_names_for_readers(self):
        """Test the human-readable part names tenets, unknown IDs verbatim"""
        text = render('peer', {'strengths': ['own', 'craft', 'retired_id'],
                               'improvements': ['delegate', 'plan']})

        assert '• Ownership\n• Craft\n• retired_id' in text
        assert text.rstrip().endswith('[/TENETS]')


class TestManagerCopyFormat:
    """Manager feedback copied from the report page."""

    def test_manager_copy_round_trip_keeps_tenets(self):
        """Test the manager's tenet picks survive paste-and-import"""
        entry = parse(render('manager', {
            'strengths': ['own', 'craft', 'clarity'],
            'improvements': ['delegate', 'plan'],
            'feedback_text': 'Great quarter overall.',
        }))

        assert entry.get_strengths() == ['own', 'craft', 'clarity']
        assert entry.get_improvements() == ['delegate', 'plan']
