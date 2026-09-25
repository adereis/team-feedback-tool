"""
Butterfly chart math in static/butterfly.js, run under Node.

Tests cover:
- Both sides share one scale, relative to the longest bar
- Highlighted rows follow the manager's picks
- While picking, the manager's +1 moves from the saved picks to the current ones

Skipped without Node, like tests/test_workday_format.py.
"""

import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUTTERFLY_JS = os.path.join(ROOT, 'static', 'butterfly.js')
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node is not installed')

ROWS = [
    {'id': 'own', 'name': 'Ownership', 'strength_count': 4, 'improvement_count': 1},
    {'id': 'craft', 'name': 'Craft', 'strength_count': 2, 'improvement_count': 0},
    {'id': 'plan', 'name': 'Planning', 'strength_count': 0, 'improvement_count': 2},
]


def call(function, *args):
    """Run Butterfly.<function>(*args) in Node and return its JSON result."""
    script = (f'const b = require({json.dumps(BUTTERFLY_JS)});'
              f'process.stdout.write(JSON.stringify(b.{function}(...{json.dumps(args)})));')
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


class TestLayout:

    def test_layout_scales_both_sides_to_longest_bar(self):
        """Test widths are percentages of the single longest bar, either side"""
        rows = call('layout', ROWS)

        assert [(r['strength']['width'], r['improvement']['width']) for r in rows] == [
            (100, 25), (50, 0), (0, 50)]

    def test_layout_without_feedback_draws_empty_bars(self):
        """Test all-zero counts give zero widths instead of dividing by zero"""
        rows = call('layout', [{'id': 'own', 'name': 'Ownership',
                                'strength_count': 0, 'improvement_count': 0}])

        assert rows[0]['strength']['width'] == 0
        assert rows[0]['improvement']['width'] == 0

    def test_layout_marks_picked_sides_only(self):
        """Test a pick highlights its own side of its own row"""
        rows = call('layout', ROWS, {'strengths': ['own'], 'improvements': ['plan']})

        assert [(r['strength']['picked'], r['improvement']['picked']) for r in rows] == [
            (True, False), (False, False), (False, True)]


class TestWithPicks:

    def test_with_picks_moves_manager_count_to_current_picks(self):
        """Test a changed pick takes its +1 along with it"""
        saved = {'strengths': ['own'], 'improvements': []}
        current = {'strengths': ['craft'], 'improvements': ['plan']}

        rows = call('withPicks', ROWS, saved, current)

        assert [(r['strength_count'], r['improvement_count']) for r in rows] == [
            (3, 1), (3, 0), (0, 3)]

    def test_with_picks_unchanged_picks_keep_counts_and_order(self):
        """Test the server's counts stand while the picks match the saved ones"""
        picks = {'strengths': ['own'], 'improvements': ['plan']}

        assert call('withPicks', ROWS, picks, picks) == ROWS
