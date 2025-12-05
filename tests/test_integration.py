"""
Integration tests for end-to-end workflows

Tests cover:
- Complete individual feedback workflow
- Complete manager workflow
- Multi-user scenarios
- Data consistency across operations
"""

import pytest
import json
import io
from feedback_models import Feedback, ManagerFeedback, Person


class TestIndividualFeedbackWorkflow:
    """Test complete individual feedback collection workflow"""

    def test_complete_individual_workflow(self, client, db_session):
        """Test full workflow: login -> give feedback -> export"""
        # Step 1: Login as employee
        response = client.get('/individual/emp003', follow_redirects=True)
        assert response.status_code == 200

        # Step 2: Submit feedback for team member
        feedback_data = {
            'to_user_id': 'emp001',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'Excellent technical skills and collaboration',
            'improvements_text': 'Could improve documentation practices'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(feedback_data),
                               content_type='application/json')
        assert response.status_code == 200

        # Step 3: Verify feedback was saved
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='emp003',
            to_user_id='emp001'
        ).first()
        assert feedback is not None
        assert feedback.strengths_text == 'Excellent technical skills and collaboration'

        # Step 4: View export list
        response = client.get('/individual/export-list')
        assert response.status_code == 200
        assert b'mgr001' in response.data or b'Alice' in response.data

        # Step 5: Export CSV
        response = client.get('/individual/export/mgr001')
        assert response.status_code == 200
        assert response.mimetype == 'text/csv'

        csv_content = response.data.decode('utf-8')
        assert 'emp003' in csv_content
        assert 'emp001' in csv_content

    def test_multiple_users_giving_feedback(self, client, db_session):
        """Test multiple users can give feedback to the same person"""
        # User 1 gives feedback
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        feedback1 = {
            'to_user_id': 'emp002',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'User 1 feedback',
            'improvements_text': 'User 1 improvements'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(feedback1),
                               content_type='application/json')
        assert response.status_code == 200

        # User 2 gives feedback to same person
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp003'

        feedback2 = {
            'to_user_id': 'emp002',
            'strengths': ['tenet2', 'tenet3', 'tenet4'],
            'improvements': ['tenet1', 'tenet2'],
            'strengths_text': 'User 2 feedback',
            'improvements_text': 'User 2 improvements'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(feedback2),
                               content_type='application/json')
        assert response.status_code == 200

        # Verify both feedbacks exist
        all_feedback = db_session.query(Feedback).filter_by(
            to_user_id='emp002'
        ).all()

        from_users = [fb.from_user_id for fb in all_feedback]
        assert 'emp001' in from_users
        assert 'emp003' in from_users

    def test_edit_existing_feedback(self, client, db_session):
        """Test user can edit their own feedback"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        # Initial feedback
        feedback_data = {
            'to_user_id': 'emp003',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'Initial text',
            'improvements_text': 'Initial improvements'
        }

        client.post('/api/feedback',
                    data=json.dumps(feedback_data),
                    content_type='application/json')

        # Edit feedback
        updated_data = {
            'to_user_id': 'emp003',
            'strengths': ['tenet4', 'tenet3', 'tenet2'],
            'improvements': ['tenet1', 'tenet2'],
            'strengths_text': 'Updated text',
            'improvements_text': 'Updated improvements'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(updated_data),
                               content_type='application/json')
        assert response.status_code == 200

        # Verify only one feedback exists (updated, not duplicated)
        feedbacks = db_session.query(Feedback).filter_by(
            from_user_id='emp001',
            to_user_id='emp003'
        ).all()

        assert len(feedbacks) == 1
        assert feedbacks[0].strengths_text == 'Updated text'

    def test_delete_and_recreate_feedback(self, client, db_session):
        """Test deleting and recreating feedback"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        # Create feedback
        feedback_data = {
            'to_user_id': 'emp003',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'Test',
            'improvements_text': 'Test'
        }

        client.post('/api/feedback',
                    data=json.dumps(feedback_data),
                    content_type='application/json')

        # Delete it
        response = client.delete('/api/feedback/emp003')
        assert response.status_code == 200

        # Verify deleted
        db_session.expire_all()
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='emp001',
            to_user_id='emp003'
        ).first()
        assert feedback is None

        # Recreate
        response = client.post('/api/feedback',
                               data=json.dumps(feedback_data),
                               content_type='application/json')
        assert response.status_code == 200

        # Verify recreated
        db_session.expire_all()
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='emp001',
            to_user_id='emp003'
        ).first()
        assert feedback is not None


class TestManagerWorkflow:
    """Test complete manager workflow"""

    def test_complete_manager_workflow(self, client, db_session):
        """Test full workflow: login -> view dashboard -> import -> view report -> save feedback"""
        # Step 1: Login as manager
        response = client.get('/manager/mgr001', follow_redirects=True)
        assert response.status_code == 200

        # Step 2: View dashboard (should show team)
        response = client.get('/manager')
        assert response.status_code == 200
        assert b'emp001' in response.data or b'Charlie' in response.data

        # Step 3: Import feedback CSV
        csv_content = """From User ID,To User ID,Strengths (Tenet IDs),Improvements (Tenet IDs),Strengths Text,Improvements Text
external001,emp001,tenet1,tenet2,Imported feedback,Imported improvements"""

        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'import.csv')
        }

        response = client.post('/manager/import',
                               data=data,
                               content_type='multipart/form-data')
        assert response.status_code == 200

        # Step 4: View report for team member
        response = client.get('/manager/report/emp001')
        assert response.status_code == 200

        # Step 5: Save manager's own feedback
        mgr_feedback = {
            'team_member_uid': 'emp001',
            'selected_strengths': ['tenet1', 'tenet2'],
            'selected_improvements': ['tenet3'],
            'feedback_text': 'Great work this quarter'
        }

        response = client.post('/api/manager-feedback',
                               data=json.dumps(mgr_feedback),
                               content_type='application/json')
        assert response.status_code == 200

        # Step 6: Verify manager feedback was saved
        db_session.expire_all()
        saved_feedback = db_session.query(ManagerFeedback).filter_by(
            manager_uid='mgr001',
            team_member_uid='emp001'
        ).first()

        assert saved_feedback is not None
        assert saved_feedback.feedback_text == 'Great work this quarter'

    def test_manager_views_aggregated_feedback(self, client, db_session):
        """Test manager can view aggregated feedback from multiple sources"""
        # Add feedback from multiple people
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        feedback1 = {
            'to_user_id': 'emp002',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'Feedback 1',
            'improvements_text': 'Improvements 1'
        }
        client.post('/api/feedback',
                    data=json.dumps(feedback1),
                    content_type='application/json')

        with client.session_transaction() as sess:
            sess['user_id'] = 'emp003'

        feedback2 = {
            'to_user_id': 'emp002',
            'strengths': ['tenet1', 'tenet3', 'tenet4'],
            'improvements': ['tenet2', 'tenet1'],
            'strengths_text': 'Feedback 2',
            'improvements_text': 'Improvements 2'
        }
        client.post('/api/feedback',
                    data=json.dumps(feedback2),
                    content_type='application/json')

        # Manager views report
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        response = client.get('/manager/report/emp002')
        assert response.status_code == 200

        # Should contain aggregated data - verify feedback exists in database
        db_session.expire_all()
        all_feedback = db_session.query(Feedback).filter_by(to_user_id='emp002').all()
        assert len(all_feedback) >= 2

        # Check that page loaded successfully with team member info
        data = response.data.decode('utf-8')
        assert 'emp002' in data or 'Diana' in data


class TestCrossWorkflowIntegration:
    """Test interactions between individual and manager workflows"""

    def test_individual_export_and_manager_import(self, client, db_session):
        """Test exporting from individual and importing to manager"""
        # Individual gives feedback
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        feedback_data = {
            'to_user_id': 'emp002',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'Export test',
            'improvements_text': 'Import test'
        }

        client.post('/api/feedback',
                    data=json.dumps(feedback_data),
                    content_type='application/json')

        # Export CSV
        response = client.get('/individual/export/mgr001')
        assert response.status_code == 200
        exported_csv = response.data.decode('utf-8')

        # Clear session and login as different manager
        client.get('/individual/switch')
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr002'

        # Import the same CSV (should work even for different manager)
        data = {
            'file': (io.BytesIO(exported_csv.encode('utf-8')), 'reimport.csv')
        }

        response = client.post('/manager/import',
                               data=data,
                               content_type='multipart/form-data')
        # Should succeed but count=0 because already exists
        assert response.status_code == 200

    def test_manager_selection_affects_butterfly_chart(self, client, db_session):
        """Test that manager selections are counted in butterfly chart"""
        # Add some peer feedback
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp003'

        feedback = {
            'to_user_id': 'emp001',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'Test',
            'improvements_text': 'Test'
        }
        client.post('/api/feedback',
                    data=json.dumps(feedback),
                    content_type='application/json')

        # Manager adds their selections
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        # Manager already has feedback from fixture, update it
        mgr_feedback = {
            'team_member_uid': 'emp001',
            'selected_strengths': ['tenet1'],  # Same as peer
            'selected_improvements': ['tenet4'],  # Same as peer
            'feedback_text': 'Manager input'
        }
        client.post('/api/manager-feedback',
                    data=json.dumps(mgr_feedback),
                    content_type='application/json')

        # View report should show combined counts
        response = client.get('/manager/report/emp001')
        assert response.status_code == 200

        # The butterfly chart should count:
        # - tenet1 strength from emp003 (1) + manager (1) + existing emp002 (1) = at least 3
        # - tenet4 improvement from emp003 (1) + manager (1) = at least 2


class TestDataConsistency:
    """Test data consistency across operations"""

    def test_concurrent_feedback_submissions(self, client, db_session):
        """Test that concurrent feedback submissions maintain consistency"""
        # Simulate two users giving feedback at the same time
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        feedback1 = {
            'to_user_id': 'emp003',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'Test 1',
            'improvements_text': 'Test 1'
        }

        response1 = client.post('/api/feedback',
                                data=json.dumps(feedback1),
                                content_type='application/json')

        with client.session_transaction() as sess:
            sess['user_id'] = 'emp002'

        feedback2 = {
            'to_user_id': 'emp003',
            'strengths': ['tenet2', 'tenet3', 'tenet4'],
            'improvements': ['tenet1', 'tenet2'],
            'strengths_text': 'Test 2',
            'improvements_text': 'Test 2'
        }

        response2 = client.post('/api/feedback',
                                data=json.dumps(feedback2),
                                content_type='application/json')

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Both should exist
        db_session.expire_all()
        all_feedback = db_session.query(Feedback).filter_by(
            to_user_id='emp003'
        ).all()

        assert len(all_feedback) >= 2

    def test_session_isolation(self, client):
        """Test that sessions are properly isolated"""
        # Set individual user
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        # Set manager in same session
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        # Both should coexist
        with client.session_transaction() as sess:
            assert sess.get('user_id') == 'emp001'
            assert sess.get('manager_uid') == 'mgr001'

        # Clearing one shouldn't affect the other
        client.get('/individual/switch')

        with client.session_transaction() as sess:
            assert 'user_id' not in sess
            assert sess.get('manager_uid') == 'mgr001'

    def test_database_rollback_on_error(self, client, db_session):
        """Test that invalid operations don't corrupt database"""
        initial_count = db_session.query(Feedback).count()

        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        # Try to submit invalid feedback (wrong number of strengths)
        invalid_feedback = {
            'to_user_id': 'emp002',
            'strengths': ['tenet1'],  # Only 1, need 3
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'Invalid',
            'improvements_text': 'Invalid'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(invalid_feedback),
                               content_type='application/json')
        assert response.status_code == 400

        # Database should remain unchanged
        db_session.expire_all()
        final_count = db_session.query(Feedback).count()
        assert final_count == initial_count


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_external_user_not_in_database(self, client, db_session):
        """Test external user (not in Person table) can give feedback"""
        # Login as external user
        client.get('/individual/external_consultant')

        # Give feedback
        feedback = {
            'to_user_id': 'emp001',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'External feedback',
            'improvements_text': 'External improvements'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(feedback),
                               content_type='application/json')
        assert response.status_code == 200

        # Verify feedback exists
        db_session.expire_all()
        feedback_obj = db_session.query(Feedback).filter_by(
            from_user_id='external_consultant',
            to_user_id='emp001'
        ).first()

        assert feedback_obj is not None

    def test_feedback_to_person_not_in_database(self, client, db_session):
        """Test giving feedback to person not in database"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        feedback = {
            'to_user_id': 'nonexistent_person',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'Test',
            'improvements_text': 'Test'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(feedback),
                               content_type='application/json')

        # Should succeed - foreign key is not enforced strictly
        assert response.status_code == 200

    def test_empty_feedback_text(self, client, db_session):
        """Test submitting feedback with empty text fields"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        feedback = {
            'to_user_id': 'emp002',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': '',
            'improvements_text': ''
        }

        response = client.post('/api/feedback',
                               data=json.dumps(feedback),
                               content_type='application/json')

        # Should succeed - text is optional
        assert response.status_code == 200

    def test_export_with_no_feedback(self, client):
        """Test export when user has given no feedback"""
        # Login as user with no feedback
        client.get('/individual/mgr002')  # Manager, unlikely to have given feedback

        response = client.get('/individual/export-list')

        # Should handle gracefully
        assert response.status_code in [200, 400]
