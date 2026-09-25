"""
Tests for the structure of rendered pages.

Tests cover:
- Page styles are emitted as their own <style> elements, never nested
- Typed text sits alone in an element that keeps its line breaks
- Links and fetches follow the mode that served the page
- Errors render as styled pages with a way back, never bare text
- Markup stays balanced, and pages never open browser dialogs
- Counts read as real plurals ("1 entry", "3 entries"), never "entry(s)"
"""

import glob
import os
import re
import sys
from html.parser import HTMLParser

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Feedback, ManagerFeedback, Person


class StyleCollector(HTMLParser):
    """Collect the raw text of every <style> element on a page."""

    def __init__(self):
        super().__init__()
        self.styles = []
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        if tag == 'style':
            self._in_style = True
            self.styles.append('')

    def handle_endtag(self, tag):
        if tag == 'style':
            self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            self.styles[-1] += data


class DivCounter(HTMLParser):
    """Track <div> nesting; ends at zero depth when every div is closed."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.lowest = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'div':
            self.depth += 1

    def handle_endtag(self, tag):
        if tag == 'div':
            self.depth -= 1
            self.lowest = min(self.lowest, self.depth)


def styles_of(html):
    collector = StyleCollector()
    collector.feed(html)
    return collector.styles


TEMPLATES = sorted(glob.glob(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates', '*.html')))

# (session key, value, path): one entry per page template in local mode
PAGES = [
    (None, None, '/'),
    (None, None, '/individual'),
    ('user_id', 'emp001', '/individual'),
    (None, None, '/manager'),
    ('manager_uid', 'mgr001', '/manager'),
    ('manager_uid', 'mgr001', '/manager/report/emp001'),
    (None, None, '/feedback'),
    (None, None, '/feedback?for=Pat%20Example'),
]


def render(client, key, value, path):
    if key:
        with client.session_transaction() as sess:
            sess[key] = value
    response = client.get(path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


class TestPageStyles:
    """Tests for how page CSS reaches the browser."""

    @pytest.mark.parametrize('key,value,path', PAGES)
    def test_page_styles_never_nested(self, client, key, value, path):
        """Test no <style> text sits inside another <style> element.

        A nested tag is raw text to the browser; it merges into the next
        selector and silently drops the page's first CSS rule.
        """
        html = render(client, key, value, path)

        for css in styles_of(html):
            assert '<style' not in css


class TestMarkup:
    """Tests for the markup every page produces."""

    @pytest.mark.parametrize('key,value,path', PAGES)
    def test_page_divs_balanced(self, client, key, value, path):
        """Test every <div> a page opens is closed, and none closes early"""
        counter = DivCounter()
        counter.feed(render(client, key, value, path))

        assert (counter.depth, counter.lowest) == (0, 0)

    def test_individual_empty_state_skips_form_script(self, client, db_session):
        """Test the import-only page ships no script for the absent form and list.

        That script looks up the feedback list at load; on this page the list
        does not exist, and the lookup would throw.
        """
        db_session.query(Feedback).delete()
        db_session.query(ManagerFeedback).delete()
        db_session.query(Person).filter(Person.user_id != 'emp001').delete()
        db_session.commit()

        html = render(client, 'user_id', 'emp001', '/individual')

        assert 'Import Orgchart to Get Started' in html
        assert 'renderFeedbackList' not in html

    @pytest.mark.parametrize('path', TEMPLATES, ids=os.path.basename)
    def test_template_opens_no_browser_dialogs(self, path):
        """Test pages report and confirm inline, never with alert/confirm/prompt"""
        with open(path) as f:
            source = f.read()

        assert re.findall(r'\b(?:alert|confirm|prompt)\(', source) == []


class TestReportLayout:
    """Tests for the order of the manager's report page."""

    def test_report_puts_manager_work_before_comments(self, client):
        """Test the chart, the manager's picks and the export come before the
        peer comments, so the manager's work is not below every comment."""
        html = render(client, 'manager_uid', 'mgr001', '/manager/report/emp001')

        order = [html.index(marker) for marker in (
            'id="butterflyChart"', 'id="your-feedback"', 'id="export"', 'id="peer-comments"')]
        assert order == sorted(order)
        for anchor in ('#your-feedback', '#peer-comments', '#export'):
            assert f'href="{anchor}"' in html


class TestDashboardLayout:
    """Tests for the manager dashboard's card order."""

    def test_dashboard_with_team_lists_team_before_import(self, client):
        """Test a loaded team comes first and the Workday import card last"""
        html = render(client, 'manager_uid', 'mgr001', '/manager')

        assert html.index('<h2>Your Team</h2>') < html.index('id="workdayCard"')

    def test_dashboard_without_team_offers_import_first(self, client):
        """Test an empty dashboard leads with the import that fills it"""
        with client.session_transaction() as sess:
            sess['manager_name'] = 'Nobody Yet'
        html = client.get('/manager').get_data(as_text=True)

        assert html.index('id="workdayCard"') < html.index('<h2>Your Team</h2>')
        assert html.count('id="workdayCard"') == 1

    def test_dashboard_has_no_date_filter(self, client):
        """Test the dashboard offers no period control: nothing on it filters by date"""
        html = render(client, 'manager_uid', 'mgr001', '/manager')

        assert 'dateRangeSelect' not in html
        assert 'Time Period' not in html


class TestTypedText:
    """Tests for how text people typed is shown on pages."""

    def test_report_comment_alone_in_line_preserving_element(self, client, db_session):
        """Test a peer comment sits alone in a .user-text element.

        .user-text keeps line breaks, so any template whitespace inside it
        would show up as blank lines around the comment.
        """
        feedback = db_session.query(Feedback).filter_by(to_user_id='emp001').one()
        feedback.strengths_text = 'Owns incidents.\n\nWrites the follow-up.'
        db_session.commit()

        html = render(client, 'manager_uid', 'mgr001', '/manager/report/emp001')

        assert '<div class="user-text">Owns incidents.\n\nWrites the follow-up.</div>' in html


# A root-relative URL written into markup or JS: href="/...", fetch('/...'), ...
HARD_CODED_URL = re.compile(
    r"""(?:href|action|src)=["']/|fetch\(\s*["'`]/|location\.href\s*=\s*["'`]/|localhost:\d""")


class TestModeLinks:
    """Tests that pages never pin a URL to one mode."""

    @pytest.mark.parametrize('path', TEMPLATES, ids=os.path.basename)
    def test_template_has_no_hard_coded_urls(self, path):
        """Test templates build URLs with url_for, VIEWS_ROOT or API_PREFIX.

        A literal "/individual" or "/" sends a demo visitor to the local DB's
        pages, and a literal host only works on one machine.
        """
        with open(path) as f:
            source = f.read()

        assert HARD_CODED_URL.findall(source) == []

    @pytest.mark.parametrize('path', ['/demo/individual', '/demo/manager'])
    def test_demo_page_links_home_to_demo(self, client, demo_db, path):
        """Test "Back to Home" on a demo page returns to the demo home"""
        html = client.get(path).get_data(as_text=True)

        assert re.search(r'<a href="/demo"[^>]*>(?:←|&larr;) Back to Home', html)
        assert 'href="/"' not in html


class TestErrorPages:
    """Tests that people never land on a bare text error."""

    @pytest.mark.parametrize('manager,path,status,action', [
        (None, '/manager/report/emp001', 400, ('/manager', 'Go to Manager Dashboard')),
        (None, '/manager/export-pdf/emp001', 400, ('/manager', 'Go to Manager Dashboard')),
        ('mgr001', '/manager/report', 400, ('/manager', 'Go to Manager Dashboard')),
        ('mgr001', '/manager/report/nobody', 404, ('/manager', 'Back to Dashboard')),
        ('mgr001', '/manager/report/emp003', 403, ('/manager', 'Back to Dashboard')),
        ('mgr001', '/manager/export-pdf/emp003', 403, ('/manager', 'Back to Dashboard')),
        (None, '/manager/nobody', 404, ('/manager', 'Choose a Manager')),
        (None, '/no/such/page', 404, ('/', 'Back to Home')),
    ])
    def test_error_is_styled_page_with_way_back(self, client, manager, path, status, action):
        """Test the status code is kept and the page offers the next step"""
        url, label = action
        if manager:
            with client.session_transaction() as sess:
                sess['manager_uid'] = manager

        response = client.get(path)
        html = response.get_data(as_text=True)

        assert response.status_code == status
        assert response.content_type.startswith('text/html')
        assert '<header>' in html  # the site layout, not a bare string
        assert f'<a href="{url}" class="btn">{label}</a>' in html

    def test_demo_error_links_back_into_demo(self, client, demo_db):
        """Test an error under /demo keeps the visitor in the demo"""
        html = client.get('/demo/manager/report/sbx001').get_data(as_text=True)

        assert '<a href="/demo/manager" class="btn">Go to Manager Dashboard</a>' in html

    @pytest.mark.parametrize('path', ['/api/no-such-endpoint', '/demo/api/no-such-endpoint'])
    def test_unknown_api_path_returns_json_404(self, client, path):
        """Test fetch() callers still get JSON they can parse"""
        response = client.get(path)

        assert response.status_code == 404
        assert response.get_json() == {"success": False, "error": "Not found"}


class TestPlurals:
    """Tests for how counts are worded."""

    @pytest.mark.parametrize('count,expected', [
        (0, '0 entries'), (1, '1 entry'), (2, '2 entries'),
    ])
    def test_plural_filter_words_count(self, count, expected):
        """Test the Jinja plural filter picks the word form for the count"""
        from app import plural_filter

        assert plural_filter(count, 'entry', 'entries') == expected

    def test_plural_filter_defaults_to_adding_s(self):
        """Test the plural form defaults to the singular plus an s"""
        from app import plural_filter

        assert plural_filter(3, 'manager review') == '3 manager reviews'

    @pytest.mark.parametrize('path', TEMPLATES, ids=os.path.basename)
    def test_template_has_no_parenthesized_plurals(self, path):
        """Test no template writes "feedback(s)"-style counts"""
        with open(path) as f:
            source = f.read()

        assert re.findall(r'\w\(s\)', source) == []
