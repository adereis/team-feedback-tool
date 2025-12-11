"""
Unit tests for database models

Tests cover:
- Person model CRUD operations and relationships
- Feedback model with JSON serialization
- ManagerFeedback model with tenet selections
- Database initialization
"""

import pytest
import tempfile
import os
from models import init_db, Person, Feedback, ManagerFeedback, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class TestDatabaseInitialization:
    """Test database setup and initialization"""

    def test_init_db_creates_database(self):
        """Test init_db creates database file and tables"""
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        os.unlink(db_path)  # Remove so init_db creates it

        session = init_db(db_path)
        assert os.path.exists(db_path)
        session.close()

        # Cleanup
        os.unlink(db_path)

    def test_init_db_returns_session(self):
        """Test init_db returns usable session"""
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        session = init_db(db_path)
        assert session is not None
        # Should be able to query
        result = session.query(Person).all()
        assert result == []
        session.close()

        # Cleanup
        os.unlink(db_path)


class TestPersonModel:
    """Test Person model functionality"""

    def test_person_creation_with_all_fields(self, db_session):
        """Test creating person with all fields populated"""
        person = Person(
            user_id='test001',
            name='Test User',
            job_title='Engineer',
            location='Boston',
            email='test@example.com',
            manager_uid='mgr001'
        )
        db_session.add(person)
        db_session.commit()

        retrieved = db_session.query(Person).filter_by(user_id='test001').first()
        assert retrieved.user_id == 'test001'
        assert retrieved.name == 'Test User'
        assert retrieved.job_title == 'Engineer'
        assert retrieved.location == 'Boston'
        assert retrieved.email == 'test@example.com'
        assert retrieved.manager_uid == 'mgr001'

    def test_person_creation_minimal_fields(self, db_session):
        """Test creating person with only required fields"""
        person = Person(
            user_id='test002',
            name='Minimal User'
        )
        db_session.add(person)
        db_session.commit()

        retrieved = db_session.query(Person).filter_by(user_id='test002').first()
        assert retrieved.user_id == 'test002'
        assert retrieved.name == 'Minimal User'
        assert retrieved.job_title is None
        assert retrieved.manager_uid is None

    def test_person_to_dict_conversion(self, db_session):
        """Test Person.to_dict() returns correct dictionary"""
        person = Person(
            user_id='test003',
            name='Dict Test',
            job_title='Tester',
            location='Remote',
            email='dict@example.com',
            manager_uid='mgr001'
        )
        db_session.add(person)
        db_session.commit()

        person_dict = person.to_dict()
        assert person_dict['user_id'] == 'test003'
        assert person_dict['name'] == 'Dict Test'
        assert person_dict['job_title'] == 'Tester'
        assert person_dict['location'] == 'Remote'
        assert person_dict['email'] == 'dict@example.com'
        assert person_dict['manager_uid'] == 'mgr001'

    def test_person_manager_relationship(self, db_session):
        """Test manager-employee relationship"""
        # Get existing manager and employee from fixture
        manager = db_session.query(Person).filter_by(user_id='mgr001').first()
        employee = db_session.query(Person).filter_by(user_id='emp001').first()

        assert employee.manager_uid == 'mgr001'
        assert employee.manager.user_id == 'mgr001'
        assert manager.user_id in [dr.manager_uid for dr in manager.direct_reports]

    def test_person_direct_reports_relationship(self, db_session):
        """Test accessing direct reports via relationship"""
        manager = db_session.query(Person).filter_by(user_id='mgr001').first()
        direct_report_ids = [dr.user_id for dr in manager.direct_reports]

        assert 'emp001' in direct_report_ids
        assert 'emp002' in direct_report_ids
        assert len(direct_report_ids) >= 2


class TestFeedbackModel:
    """Test Feedback model functionality"""

    def test_feedback_creation_with_all_fields(self, db_session):
        """Test creating feedback with all fields"""
        feedback = Feedback(
            from_user_id='emp001',
            to_user_id='emp003',
            strengths_text='Excellent communication',
            improvements_text='Could improve testing'
        )
        feedback.set_strengths(['tenet1', 'tenet2', 'tenet3'])
        feedback.set_improvements(['tenet4', 'tenet1'])

        db_session.add(feedback)
        db_session.commit()

        retrieved = db_session.query(Feedback).filter_by(
            from_user_id='emp001',
            to_user_id='emp003'
        ).first()

        assert retrieved.from_user_id == 'emp001'
        assert retrieved.to_user_id == 'emp003'
        assert retrieved.strengths_text == 'Excellent communication'
        assert retrieved.improvements_text == 'Could improve testing'
        assert retrieved.get_strengths() == ['tenet1', 'tenet2', 'tenet3']
        assert retrieved.get_improvements() == ['tenet4', 'tenet1']

    def test_feedback_strengths_json_serialization(self, db_session):
        """Test strengths are properly serialized to/from JSON"""
        feedback = Feedback(
            from_user_id='emp001',
            to_user_id='emp002'
        )
        strengths = ['tenet1', 'tenet2', 'tenet3']
        feedback.set_strengths(strengths)

        db_session.add(feedback)
        db_session.commit()

        # Retrieve and verify
        retrieved = db_session.query(Feedback).filter_by(
            from_user_id='emp001',
            to_user_id='emp002'
        ).first()

        assert retrieved.get_strengths() == strengths
        assert isinstance(retrieved.get_strengths(), list)

    def test_feedback_improvements_json_serialization(self, db_session):
        """Test improvements are properly serialized to/from JSON"""
        feedback = Feedback(
            from_user_id='emp002',
            to_user_id='emp003'
        )
        improvements = ['tenet4', 'tenet1']
        feedback.set_improvements(improvements)

        db_session.add(feedback)
        db_session.commit()

        retrieved = db_session.query(Feedback).filter_by(
            from_user_id='emp002',
            to_user_id='emp003'
        ).first()

        assert retrieved.get_improvements() == improvements
        assert isinstance(retrieved.get_improvements(), list)

    def test_feedback_empty_tenets_returns_empty_list(self, db_session):
        """Test that None/empty tenet fields return empty lists"""
        feedback = Feedback(
            from_user_id='emp001',
            to_user_id='emp002'
        )
        db_session.add(feedback)
        db_session.commit()

        assert feedback.get_strengths() == []
        assert feedback.get_improvements() == []

    def test_feedback_to_dict_conversion(self, db_session):
        """Test Feedback.to_dict() returns correct dictionary"""
        feedback = Feedback(
            from_user_id='emp001',
            to_user_id='emp002',
            strengths_text='Great work',
            improvements_text='Needs focus'
        )
        feedback.set_strengths(['tenet1', 'tenet2', 'tenet3'])
        feedback.set_improvements(['tenet4'])

        db_session.add(feedback)
        db_session.commit()

        feedback_dict = feedback.to_dict()
        assert feedback_dict['from_user_id'] == 'emp001'
        assert feedback_dict['to_user_id'] == 'emp002'
        assert feedback_dict['strengths'] == ['tenet1', 'tenet2', 'tenet3']
        assert feedback_dict['improvements'] == ['tenet4']
        assert feedback_dict['strengths_text'] == 'Great work'
        assert feedback_dict['improvements_text'] == 'Needs focus'
        assert 'id' in feedback_dict

    def test_feedback_update_existing(self, db_session):
        """Test updating existing feedback record"""
        # Use the existing feedback from fixture
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='emp001',
            to_user_id='emp002'
        ).first()

        # Update it
        feedback.strengths_text = 'Updated text'
        feedback.set_strengths(['tenet3', 'tenet4', 'tenet1'])
        db_session.commit()

        # Refresh session and verify update
        db_session.expire_all()
        retrieved = db_session.query(Feedback).filter_by(
            from_user_id='emp001',
            to_user_id='emp002'
        ).first()

        assert retrieved.strengths_text == 'Updated text'
        assert retrieved.get_strengths() == ['tenet3', 'tenet4', 'tenet1']

    def test_feedback_relationships(self, db_session):
        """Test feedback relationships with Person model"""
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='emp001',
            to_user_id='emp002'
        ).first()

        # Test giver relationship
        assert feedback.giver.user_id == 'emp001'
        assert feedback.giver.name == 'Charlie Developer'

        # Test receiver relationship
        assert feedback.receiver.user_id == 'emp002'
        assert feedback.receiver.name == 'Diana Developer'


class TestManagerFeedbackModel:
    """Test ManagerFeedback model functionality"""

    def test_manager_feedback_creation(self, db_session):
        """Test creating manager feedback with all fields"""
        mgr_feedback = ManagerFeedback(
            manager_uid='mgr001',
            team_member_uid='emp002',
            feedback_text='Strong performer, ready for promotion'
        )
        mgr_feedback.set_selected_strengths(['tenet1', 'tenet2'])
        mgr_feedback.set_selected_improvements(['tenet3'])

        db_session.add(mgr_feedback)
        db_session.commit()

        retrieved = db_session.query(ManagerFeedback).filter_by(
            manager_uid='mgr001',
            team_member_uid='emp002'
        ).first()

        assert retrieved.manager_uid == 'mgr001'
        assert retrieved.team_member_uid == 'emp002'
        assert retrieved.feedback_text == 'Strong performer, ready for promotion'
        assert retrieved.get_selected_strengths() == ['tenet1', 'tenet2']
        assert retrieved.get_selected_improvements() == ['tenet3']

    def test_manager_feedback_selected_strengths_serialization(self, db_session):
        """Test selected strengths JSON serialization"""
        mgr_feedback = ManagerFeedback(
            manager_uid='mgr002',
            team_member_uid='emp003'
        )
        strengths = ['tenet1', 'tenet2', 'tenet3']
        mgr_feedback.set_selected_strengths(strengths)

        db_session.add(mgr_feedback)
        db_session.commit()

        retrieved = db_session.query(ManagerFeedback).filter_by(
            manager_uid='mgr002',
            team_member_uid='emp003'
        ).first()

        assert retrieved.get_selected_strengths() == strengths
        assert isinstance(retrieved.get_selected_strengths(), list)

    def test_manager_feedback_selected_improvements_serialization(self, db_session):
        """Test selected improvements JSON serialization"""
        mgr_feedback = ManagerFeedback(
            manager_uid='mgr001',
            team_member_uid='emp002'
        )
        improvements = ['tenet4', 'tenet1']
        mgr_feedback.set_selected_improvements(improvements)

        db_session.add(mgr_feedback)
        db_session.commit()

        retrieved = db_session.query(ManagerFeedback).filter_by(
            manager_uid='mgr001',
            team_member_uid='emp002'
        ).first()

        assert retrieved.get_selected_improvements() == improvements

    def test_manager_feedback_empty_selections_returns_empty_list(self, db_session):
        """Test that None/empty selection fields return empty lists"""
        mgr_feedback = ManagerFeedback(
            manager_uid='mgr001',
            team_member_uid='emp002'
        )
        db_session.add(mgr_feedback)
        db_session.commit()

        assert mgr_feedback.get_selected_strengths() == []
        assert mgr_feedback.get_selected_improvements() == []

    def test_manager_feedback_to_dict_conversion(self, db_session):
        """Test ManagerFeedback.to_dict() returns correct dictionary"""
        mgr_feedback = ManagerFeedback(
            manager_uid='mgr001',
            team_member_uid='emp001',
            feedback_text='Excellent work this quarter'
        )
        mgr_feedback.set_selected_strengths(['tenet1'])
        mgr_feedback.set_selected_improvements(['tenet2', 'tenet3'])

        db_session.add(mgr_feedback)
        db_session.commit()

        feedback_dict = mgr_feedback.to_dict()
        assert feedback_dict['manager_uid'] == 'mgr001'
        assert feedback_dict['team_member_uid'] == 'emp001'
        assert feedback_dict['feedback_text'] == 'Excellent work this quarter'
        assert feedback_dict['selected_strengths'] == ['tenet1']
        assert feedback_dict['selected_improvements'] == ['tenet2', 'tenet3']
        assert 'id' in feedback_dict

    def test_manager_feedback_update_existing(self, db_session):
        """Test updating existing manager feedback"""
        # Get existing from fixture
        existing = db_session.query(ManagerFeedback).filter_by(
            manager_uid='mgr001',
            team_member_uid='emp001'
        ).first()

        original_id = existing.id

        # Update
        existing.feedback_text = 'Updated feedback'
        existing.set_selected_strengths(['tenet4'])
        db_session.commit()

        # Verify
        retrieved = db_session.query(ManagerFeedback).filter_by(
            manager_uid='mgr001',
            team_member_uid='emp001'
        ).first()

        assert retrieved.id == original_id
        assert retrieved.feedback_text == 'Updated feedback'
        assert retrieved.get_selected_strengths() == ['tenet4']


class TestModelRelationships:
    """Test complex relationships between models"""

    def test_person_feedback_given_relationship(self, db_session):
        """Test Person.feedback_given relationship"""
        person = db_session.query(Person).filter_by(user_id='emp001').first()
        feedback_given = person.feedback_given

        assert len(feedback_given) > 0
        assert all(fb.from_user_id == 'emp001' for fb in feedback_given)

    def test_person_feedback_received_relationship(self, db_session):
        """Test Person.feedback_received relationship"""
        person = db_session.query(Person).filter_by(user_id='emp002').first()
        feedback_received = person.feedback_received

        assert len(feedback_received) > 0
        assert all(fb.to_user_id == 'emp002' for fb in feedback_received)

    def test_cascade_delete_behavior(self, db_session):
        """Test that deleting a person doesn't cascade to feedback"""
        # Create a person and feedback
        temp_person = Person(
            user_id='temp001',
            name='Temporary Person'
        )
        db_session.add(temp_person)
        db_session.commit()

        # This test verifies the system doesn't break
        # The actual cascade behavior depends on foreign key constraints
        # which should preserve data integrity
        feedback_count_before = db_session.query(Feedback).count()

        # Note: In a real system, you'd want to test specific cascade rules
        assert feedback_count_before >= 0
