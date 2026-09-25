"""
Tests for the structure of rendered pages.

Tests cover:
- Page styles are emitted as their own <style> elements, never nested
- Typed text sits alone in an element that keeps its line breaks
- Links and fetches follow the mode that served the page
"""

import glob
import os
import re
import sys
from html.parser import HTMLParser

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Feedback


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


def styles_of(html):
    collector = StyleCollector()
    collector.feed(html)
    return collector.styles


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


TEMPLATES = sorted(glob.glob(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates', '*.html')))

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
