"""
Pytest configuration and shared fixtures for Team Feedback Tool tests

Provides test fixtures for:
- Test database with sample data
- Flask test client
- Sample tenets configuration
"""

import pytest
import tempfile
import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app
from feedback_models import init_db, Person, Feedback, ManagerFeedback, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def test_tenets_file():
    """Create temporary tenets configuration file"""
    tenets_data = {
        "version": "test-2025",
        "tenets": [
            {
                "id": "tenet1",
                "name": "Test Tenet 1",
                "category": "Testing",
                "description": "First test tenet",
                "active": True
            },
            {
                "id": "tenet2",
                "name": "Test Tenet 2",
                "category": "Testing",
                "description": "Second test tenet",
                "active": True
            },
            {
                "id": "tenet3",
                "name": "Test Tenet 3",
                "category": "Testing",
                "description": "Third test tenet",
                "active": True
            },
            {
                "id": "tenet4",
                "name": "Test Tenet 4",
                "category": "Testing",
                "description": "Fourth test tenet",
                "active": True
            },
            {
                "id": "inactive_tenet",
                "name": "Inactive Tenet",
                "category": "Testing",
                "description": "This should not appear",
                "active": False
            }
        ],
        "selection_config": {
            "strengths_count": 3,
            "improvement_count": 3,
            "allow_duplicates": False
        }
    }

    # Create temporary file
    fd, path = tempfile.mkstemp(suffix='.json')
    with os.fdopen(fd, 'w') as f:
        json.dump(tenets_data, f)

    yield path

    # Cleanup
    os.unlink(path)


@pytest.fixture
def test_db():
    """Create temporary test database with sample data"""
    # Create temporary database file
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # Initialize database
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create sample people
    manager1 = Person(
        user_id='mgr001',
        name='Alice Manager',
        job_title='Engineering Manager',
        location='Boston',
        email='alice@example.com',
        manager_uid=None
    )

    manager2 = Person(
        user_id='mgr002',
        name='Bob Manager',
        job_title='Senior Manager',
        location='Remote',
        email='bob@example.com',
        manager_uid=None
    )

    employee1 = Person(
        user_id='emp001',
        name='Charlie Developer',
        job_title='Software Engineer',
        location='Boston',
        email='charlie@example.com',
        manager_uid='mgr001'
    )

    employee2 = Person(
        user_id='emp002',
        name='Diana Developer',
        job_title='Senior Software Engineer',
        location='New York',
        email='diana@example.com',
        manager_uid='mgr001'
    )

    employee3 = Person(
        user_id='emp003',
        name='Eve Engineer',
        job_title='Software Engineer',
        location='Remote',
        email='eve@example.com',
        manager_uid='mgr002'
    )

    session.add_all([manager1, manager2, employee1, employee2, employee3])

    # Create sample feedback
    feedback1 = Feedback(
        from_user_id='emp001',
        to_user_id='emp002',
        strengths_text='Great collaboration skills',
        improvements_text='Could improve code reviews'
    )
    feedback1.set_strengths(['tenet1', 'tenet2', 'tenet3'])
    feedback1.set_improvements(['tenet4', 'tenet1'])

    feedback2 = Feedback(
        from_user_id='emp002',
        to_user_id='emp001',
        strengths_text='Excellent problem solving',
        improvements_text='Time management needs work'
    )
    feedback2.set_strengths(['tenet2', 'tenet3', 'tenet4'])
    feedback2.set_improvements(['tenet1', 'tenet2'])

    session.add_all([feedback1, feedback2])

    # Create sample manager feedback
    mgr_feedback = ManagerFeedback(
        manager_uid='mgr001',
        team_member_uid='emp001',
        feedback_text='Solid performer, ready for next level'
    )
    mgr_feedback.set_selected_strengths(['tenet1', 'tenet2'])
    mgr_feedback.set_selected_improvements(['tenet3'])

    session.add(mgr_feedback)
    session.commit()
    session.close()

    yield db_path

    # Cleanup
    os.unlink(db_path)


@pytest.fixture
def app(test_db, test_tenets_file, monkeypatch):
    """Create Flask app configured for testing"""
    # Patch the TENETS_FILE to use test file
    monkeypatch.setattr('app.TENETS_FILE', test_tenets_file)

    # Patch init_db to use test database
    def mock_init_db(db_path=None):
        engine = create_engine(f'sqlite:///{test_db}')
        Session = sessionmaker(bind=engine)
        return Session()

    monkeypatch.setattr('app.init_db', mock_init_db)

    # Configure app for testing
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'test-secret-key'

    yield flask_app


@pytest.fixture
def client(app):
    """Create test client for making requests"""
    return app.test_client()


@pytest.fixture
def session_client(client):
    """Create test client with session support"""
    with client.session_transaction() as sess:
        # Session is now available for modification
        pass
    return client


@pytest.fixture
def sample_csv_feedback():
    """Generate sample CSV feedback data"""
    csv_content = """From User ID,To User ID,Strengths (Tenet IDs),Improvements (Tenet IDs),Strengths Text,Improvements Text
emp001,emp002,tenet1,tenet2,Great work,Needs improvement
emp003,emp001,tenet2,tenet3,Excellent,Could be better"""
    return csv_content


@pytest.fixture
def db_session(test_db):
    """Create database session for direct database access in tests"""
    engine = create_engine(f'sqlite:///{test_db}')
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
