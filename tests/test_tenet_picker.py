"""
Tenet selection rules in static/tenet_picker.js, run under Node.

The picker must never produce a selection the server would reject, so one
test drives it with a long run of clicks on both lists and checks the
result against tenet_selection_error() from app.py.

Tests cover:
- A tenet picked in one list is unavailable in the other
- Lists stop growing at their maximum; clicking a picked tenet removes it
- Checklist status and wording

Skipped without Node, like tests/test_workday_format.py.
"""

import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICKER_JS = os.path.join(ROOT, 'static', 'tenet_picker.js')
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node is not installed')

EMPTY = {'strengths': [], 'improvements': []}


def call(function, *args):
    """Run TenetPicker.<function>(*args) in Node and return its JSON result."""
    script = (f'const p = require({json.dumps(PICKER_JS)});'
              f'process.stdout.write(JSON.stringify(p.{function}(...{json.dumps(args)})));')
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def clicks(sequence):
    """Apply [(kind, id), ...] clicks from an empty selection, in one Node run."""
    script = (f'const p = require({json.dumps(PICKER_JS)});'
              f'let s = {{strengths: [], improvements: []}};'
              f'for (const [k, id] of {json.dumps(sequence)}) s = p.toggle(s, k, id);'
              f'process.stdout.write(JSON.stringify(s));')
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


class TestAvailability:

    def test_availability_tenet_in_other_list_is_taken(self):
        """Test a strength cannot also be picked as an improvement"""
        selection = {'strengths': ['own'], 'improvements': []}

        assert call('availability', selection, 'improvements', 'own') == 'taken'
        assert call('availability', selection, 'strengths', 'own') == 'selected'

    def test_availability_full_list_blocks_new_tenets(self):
        """Test a fourth strength is unavailable, but picked ones stay clickable"""
        selection = {'strengths': ['a', 'b', 'c'], 'improvements': []}

        assert call('availability', selection, 'strengths', 'd') == 'full'
        assert call('availability', selection, 'strengths', 'a') == 'selected'
        assert call('availability', selection, 'improvements', 'd') == 'available'


class TestToggle:

    def test_toggle_adds_then_removes(self):
        """Test clicking a tenet twice leaves the selection as it was"""
        assert clicks([('strengths', 'a')]) == {'strengths': ['a'], 'improvements': []}
        assert clicks([('strengths', 'a'), ('strengths', 'a')]) == EMPTY

    def test_toggle_ignores_blocked_clicks(self):
        """Test clicks on full or taken tenets change nothing"""
        selection = clicks([('strengths', t) for t in 'abcd'] + [('improvements', 'a')])

        assert selection == {'strengths': ['a', 'b', 'c'], 'improvements': []}

    def test_toggle_never_exceeds_server_rule(self, app):
        """Test any click sequence stays within what the server accepts"""
        from app import tenet_selection_error

        sequence = [(kind, t) for t in 'abcdefg' for kind in ('strengths', 'improvements')]
        selection = clicks(sequence)

        assert len(selection['strengths']) <= 3
        assert len(selection['improvements']) <= 3
        assert not set(selection['strengths']) & set(selection['improvements'])
        assert tenet_selection_error(selection['strengths'], selection['improvements']) is None


class TestStatus:

    @pytest.mark.parametrize('strengths,improvements,complete', [
        (3, 2, True), (3, 3, True), (3, 1, False), (2, 3, False), (0, 0, False),
    ])
    def test_status_complete_matches_rule(self, strengths, improvements, complete):
        """Test "complete" means exactly 3 strengths and 2-3 improvements"""
        selection = {'strengths': [f's{i}' for i in range(strengths)],
                     'improvements': [f'i{i}' for i in range(improvements)]}

        assert call('status', selection)['complete'] is complete

    def test_status_wording_counts_toward_range(self):
        """Test the improvement count reads as done at 2, not as "2/3" to go"""
        status = call('status', {'strengths': ['a', 'b'], 'improvements': ['c', 'd']})

        assert status['strengthsText'] == 'Select 3 strengths (2 of 3)'
        assert status['improvementsText'] == 'Select 2 or 3 improvements (2 selected)'
        assert status['improvementsDone'] is True
