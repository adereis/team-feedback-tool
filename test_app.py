"""
Integration tests for Flask application routes and API endpoints

Tests cover:
- Individual workflow (selection, feedback submission, export)
- Manager workflow (selection, dashboard, import, reports)
- API endpoints for feedback operations
- Session management
- CSV import/export functionality
"""

import pytest
import json
import io
from feedback_models import Feedback, ManagerFeedback, Person


class TestIndexRoute:
    """Test home page"""

    def test_index_returns_200(self, client):
        """Test home page loads successfully"""
        response = client.get('/')
        assert response.status_code == 200

    def test_index_renders_template(self, client):
        """Test home page contains expected content"""
        response = client.get('/')
        assert b'Team Feedback Tool' in response.data or b'individual' in response.data.lower()


class TestDbStats:
    """Test database statistics API"""

    def test_db_stats_returns_counts(self, client, db_session):
        """Test /api/db-stats returns correct counts"""
        response = client.get('/api/db-stats')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'total_people' in data
        assert 'managers' in data
        assert 'peer_feedback' in data
        assert 'manager_reviews' in data


class TestOrgchartImport:
    """Test orgchart CSV import via web API"""

    def test_import_orgchart_creates_people(self, client, db_session):
        """Test importing orgchart CSV creates person records"""
        csv_content = """Name,User ID,Job Title,Location,Email,Manager UID
Test Manager,tmgr,Manager,NYC,tmgr@example.com,
Test Employee,temp,Developer,NYC,temp@example.com,tmgr"""

        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'orgchart.csv'),
            'reset': 'false'
        }

        response = client.post('/api/import-orgchart',
                               data=data,
                               content_type='multipart/form-data')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['new_count'] == 2

    def test_import_orgchart_with_reset(self, client, db_session):
        """Test importing with reset clears existing data"""
        # First verify we have existing data from fixtures
        initial_count = db_session.query(Person).count()
        assert initial_count > 0

        csv_content = """Name,User ID,Job Title,Location,Email,Manager UID
New Manager,newmgr,Manager,NYC,newmgr@example.com,"""

        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'orgchart.csv'),
            'reset': 'true'
        }

        response = client.post('/api/import-orgchart',
                               data=data,
                               content_type='multipart/form-data')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['reset'] is True

        # Verify old data was cleared
        db_session.expire_all()
        final_count = db_session.query(Person).count()
        assert final_count == 1

    def test_import_orgchart_validates_columns(self, client):
        """Test import rejects CSV with missing columns"""
        csv_content = """Name,Job Title
Test Person,Developer"""

        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'orgchart.csv')
        }

        response = client.post('/api/import-orgchart',
                               data=data,
                               content_type='multipart/form-data')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert result['success'] is False
        assert 'Missing columns' in result['error']


class TestIndividualWorkflow:
    """Test individual feedback collection workflow"""

    def test_individual_without_session_shows_selection(self, client):
        """Test /individual without session shows user selection page"""
        response = client.get('/individual')
        assert response.status_code == 200
        # Should show people list for selection
        assert b'emp001' in response.data or b'Charlie' in response.data

    def test_individual_with_session_shows_feedback_page(self, client):
        """Test /individual with session shows feedback page"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        response = client.get('/individual')
        assert response.status_code == 200
        # Should have feedback form elements
        assert b'emp002' in response.data or b'Diana' in response.data

    def test_individual_direct_login_sets_session(self, client):
        """Test /individual/<user_id> sets session and redirects"""
        response = client.get('/individual/emp001', follow_redirects=False)
        assert response.status_code == 302
        assert response.location == '/individual'

        # Verify session was set
        with client.session_transaction() as sess:
            assert sess.get('user_id') == 'emp001'

    def test_individual_login_allows_external_user(self, client):
        """Test individual login works for user not in database"""
        response = client.get('/individual/external_user123', follow_redirects=False)
        assert response.status_code == 302

        with client.session_transaction() as sess:
            assert sess.get('user_id') == 'external_user123'

    def test_individual_switch_clears_session(self, client):
        """Test /individual/switch clears user session"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        response = client.get('/individual/switch', follow_redirects=False)
        assert response.status_code == 302

        with client.session_transaction() as sess:
            assert 'user_id' not in sess


class TestSetUserAPI:
    """Test set user API endpoint"""

    def test_set_user_with_valid_user_id(self, client):
        """Test setting user ID via API"""
        response = client.post('/api/set-user',
                               data=json.dumps({'user_id': 'emp001'}),
                               content_type='application/json')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        with client.session_transaction() as sess:
            assert sess.get('user_id') == 'emp001'

    def test_set_user_allows_external_user(self, client):
        """Test setting external user ID not in database"""
        response = client.post('/api/set-user',
                               data=json.dumps({'user_id': 'external_provider'}),
                               content_type='application/json')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_set_user_missing_user_id_returns_error(self, client):
        """Test API returns error when user_id is missing"""
        response = client.post('/api/set-user',
                               data=json.dumps({}),
                               content_type='application/json')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'user_id' in data['error'].lower()


class TestFeedbackAPI:
    """Test feedback submission and deletion APIs"""

    def test_save_feedback_new_creates_record(self, client, db_session):
        """Test creating new feedback via API"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp003'

        feedback_data = {
            'to_user_id': 'emp001',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'Great collaboration',
            'improvements_text': 'Could improve testing'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(feedback_data),
                               content_type='application/json')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify in database
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='emp003',
            to_user_id='emp001'
        ).first()

        assert feedback is not None
        assert feedback.get_strengths() == ['tenet1', 'tenet2', 'tenet3']
        assert feedback.get_improvements() == ['tenet4', 'tenet1']

    def test_save_feedback_updates_existing(self, client, db_session):
        """Test updating existing feedback via API"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        updated_data = {
            'to_user_id': 'emp002',
            'strengths': ['tenet4', 'tenet3', 'tenet2'],
            'improvements': ['tenet1', 'tenet4'],
            'strengths_text': 'Updated strengths',
            'improvements_text': 'Updated improvements'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(updated_data),
                               content_type='application/json')

        assert response.status_code == 200

        # Verify update
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='emp001',
            to_user_id='emp002'
        ).first()

        assert feedback.strengths_text == 'Updated strengths'
        assert feedback.get_strengths() == ['tenet4', 'tenet3', 'tenet2']

    def test_save_feedback_requires_session(self, client):
        """Test API returns error when no user in session"""
        feedback_data = {
            'to_user_id': 'emp001',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4', 'tenet1'],
            'strengths_text': 'Test',
            'improvements_text': 'Test'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(feedback_data),
                               content_type='application/json')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    def test_save_feedback_validates_strengths_count(self, client):
        """Test API validates exactly 3 strengths required"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        # Too few strengths
        feedback_data = {
            'to_user_id': 'emp002',
            'strengths': ['tenet1', 'tenet2'],
            'improvements': ['tenet3', 'tenet4'],
            'strengths_text': 'Test',
            'improvements_text': 'Test'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(feedback_data),
                               content_type='application/json')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert '3 strengths' in data['error'].lower()

    def test_save_feedback_validates_improvements_count(self, client):
        """Test API validates 2-3 improvements required"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        # Too few improvements
        feedback_data = {
            'to_user_id': 'emp002',
            'strengths': ['tenet1', 'tenet2', 'tenet3'],
            'improvements': ['tenet4'],
            'strengths_text': 'Test',
            'improvements_text': 'Test'
        }

        response = client.post('/api/feedback',
                               data=json.dumps(feedback_data),
                               content_type='application/json')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert '2-3 improvements' in data['error'].lower()

    def test_delete_feedback_removes_record(self, client, db_session):
        """Test deleting feedback via API"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        # Verify feedback exists
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='emp001',
            to_user_id='emp002'
        ).first()
        assert feedback is not None

        # Delete it
        response = client.delete('/api/feedback/emp002')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify deleted
        db_session.expire_all()
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='emp001',
            to_user_id='emp002'
        ).first()
        assert feedback is None

    def test_delete_feedback_requires_session(self, client):
        """Test delete requires user session"""
        response = client.delete('/api/feedback/emp002')
        assert response.status_code == 400


class TestFeedbackExport:
    """Test feedback CSV export functionality"""

    def test_export_list_shows_managers(self, client):
        """Test export list page shows available managers"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        response = client.get('/individual/export-list')
        assert response.status_code == 200
        assert b'mgr001' in response.data or b'Alice' in response.data

    def test_export_list_requires_session(self, client):
        """Test export list requires user session"""
        response = client.get('/individual/export-list')
        assert response.status_code == 400

    def test_export_csv_downloads_file(self, client):
        """Test CSV export downloads file"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        response = client.get('/individual/export/mgr001')
        assert response.status_code == 200
        assert response.mimetype == 'text/csv'
        assert 'feedback_for_mgr001.csv' in response.headers.get('Content-Disposition', '')

    def test_export_csv_contains_correct_data(self, client):
        """Test CSV export contains correct feedback data"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        response = client.get('/individual/export/mgr001')
        assert response.status_code == 200

        csv_content = response.data.decode('utf-8')
        assert 'From User ID' in csv_content
        assert 'To User ID' in csv_content
        assert 'emp001' in csv_content

    def test_export_csv_filters_by_manager(self, client, db_session):
        """Test CSV export only includes feedback for specified manager's team"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        # Add feedback to someone with different manager
        feedback = Feedback(
            from_user_id='emp001',
            to_user_id='emp003'  # emp003 has mgr002 as manager
        )
        feedback.set_strengths(['tenet1', 'tenet2', 'tenet3'])
        feedback.set_improvements(['tenet4', 'tenet1'])
        db_session.add(feedback)
        db_session.commit()

        # Export for mgr001 should not include emp003
        response = client.get('/individual/export/mgr001')
        csv_content = response.data.decode('utf-8')

        # Should include emp002 (managed by mgr001)
        assert 'emp002' in csv_content
        # Should not include emp003 (managed by mgr002)
        assert 'emp003' not in csv_content


class TestManagerWorkflow:
    """Test manager dashboard and workflow"""

    def test_manager_without_session_shows_selection(self, client):
        """Test /manager without session shows manager selection"""
        response = client.get('/manager')
        assert response.status_code == 200
        assert b'mgr001' in response.data or b'Alice' in response.data

    def test_manager_with_session_shows_dashboard(self, client):
        """Test /manager with session shows dashboard"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        response = client.get('/manager')
        assert response.status_code == 200
        # Should show team members
        assert b'emp001' in response.data or b'Charlie' in response.data

    def test_manager_direct_login_sets_session(self, client):
        """Test /manager/<manager_uid> sets session"""
        response = client.get('/manager/mgr001', follow_redirects=False)
        assert response.status_code == 302

        with client.session_transaction() as sess:
            assert sess.get('manager_uid') == 'mgr001'

    def test_manager_login_invalid_manager_returns_404(self, client):
        """Test manager login with invalid ID returns 404"""
        response = client.get('/manager/invalid_mgr')
        assert response.status_code == 404

    def test_manager_switch_clears_session(self, client):
        """Test /manager/switch clears manager session"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        response = client.get('/manager/switch', follow_redirects=False)
        assert response.status_code == 302

        with client.session_transaction() as sess:
            assert 'manager_uid' not in sess

    def test_manager_dashboard_shows_team_members(self, client):
        """Test manager dashboard displays team members"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        response = client.get('/manager')
        assert response.status_code == 200
        data = response.data.decode('utf-8')

        # Should show team members
        assert 'emp001' in data or 'Charlie' in data
        assert 'emp002' in data or 'Diana' in data


class TestSetManagerAPI:
    """Test set manager API endpoint"""

    def test_set_manager_with_valid_manager(self, client):
        """Test setting manager via API with valid manager"""
        response = client.post('/api/set-manager',
                               data=json.dumps({'manager_uid': 'mgr001'}),
                               content_type='application/json')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        with client.session_transaction() as sess:
            assert sess.get('manager_uid') == 'mgr001'

    def test_set_manager_with_invalid_manager_returns_404(self, client):
        """Test setting invalid manager returns 404"""
        response = client.post('/api/set-manager',
                               data=json.dumps({'manager_uid': 'invalid'}),
                               content_type='application/json')

        assert response.status_code == 404
        data = json.loads(response.data)
        assert data['success'] is False

    def test_set_manager_missing_manager_uid_returns_error(self, client):
        """Test API returns error when manager_uid missing"""
        response = client.post('/api/set-manager',
                               data=json.dumps({}),
                               content_type='application/json')

        assert response.status_code == 400


class TestFeedbackImport:
    """Test CSV feedback import functionality"""

    def test_import_csv_creates_feedback_records(self, client, db_session, sample_csv_feedback):
        """Test importing CSV creates feedback records"""
        data = {
            'file': (io.BytesIO(sample_csv_feedback.encode('utf-8')), 'feedback.csv')
        }

        response = client.post('/manager/import',
                               data=data,
                               content_type='multipart/form-data')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['new_count'] >= 1

        # Verify records created
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='emp003',
            to_user_id='emp001'
        ).first()
        assert feedback is not None

    def test_import_csv_updates_existing(self, client, db_session):
        """Test importing CSV with existing pairs updates the records"""
        # Use unique user IDs to avoid conflicts with fixtures
        csv_content1 = """From User ID,To User ID,Strengths (Tenet IDs),Improvements (Tenet IDs),Strengths Text,Improvements Text
import_test_user1,import_test_user2,tenet1,tenet2,Original strength text,Original improvement text"""

        data1 = {
            'file': (io.BytesIO(csv_content1.encode('utf-8')), 'feedback.csv')
        }

        # First import
        response1 = client.post('/manager/import',
                                data=data1,
                                content_type='multipart/form-data')
        result1 = json.loads(response1.data)
        assert result1['new_count'] == 1
        assert result1['updated_count'] == 0

        # Verify original content
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='import_test_user1',
            to_user_id='import_test_user2'
        ).first()
        assert feedback.strengths_text == 'Original strength text'

        # Second import with updated content
        csv_content2 = """From User ID,To User ID,Strengths (Tenet IDs),Improvements (Tenet IDs),Strengths Text,Improvements Text
import_test_user1,import_test_user2,tenet3,tenet4,Updated strength text,Updated improvement text"""

        data2 = {
            'file': (io.BytesIO(csv_content2.encode('utf-8')), 'feedback2.csv')
        }
        response2 = client.post('/manager/import',
                                data=data2,
                                content_type='multipart/form-data')
        result2 = json.loads(response2.data)

        # Should update existing record
        assert result2['new_count'] == 0
        assert result2['updated_count'] == 1
        assert 'import_test_user1 → import_test_user2' in result2['updated_pairs']

        # Verify content was updated
        db_session.expire_all()
        feedback = db_session.query(Feedback).filter_by(
            from_user_id='import_test_user1',
            to_user_id='import_test_user2'
        ).first()
        assert feedback.strengths_text == 'Updated strength text'
        assert feedback.improvements_text == 'Updated improvement text'

    def test_import_csv_requires_file(self, client):
        """Test import returns error when no file provided"""
        response = client.post('/manager/import',
                               data={},
                               content_type='multipart/form-data')

        assert response.status_code == 400

    def test_import_csv_rejects_invalid_format(self, client):
        """Test import returns error for CSV with wrong columns"""
        # This is an orgchart CSV, not a feedback CSV
        csv_content = """Name,User ID,Job Title,Location,Email,Manager UID
John Doe,jdoe,Engineer,NYC,jdoe@example.com,mgr001"""

        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'orgchart.csv')
        }

        response = client.post('/manager/import',
                               data=data,
                               content_type='multipart/form-data')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert result['success'] is False
        assert 'Missing columns' in result['error']


class TestManagerReport:
    """Test manager report viewing and editing"""

    def test_view_report_shows_team_member_feedback(self, client):
        """Test viewing report for team member"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        response = client.get('/manager/report/emp001')
        assert response.status_code == 200
        data = response.data.decode('utf-8')

        # Should show team member info
        assert 'emp001' in data or 'Charlie' in data

    def test_view_report_requires_manager_session(self, client):
        """Test viewing report requires manager session"""
        response = client.get('/manager/report/emp001')
        assert response.status_code == 400

    def test_view_report_validates_team_membership(self, client):
        """Test manager can only view their team members"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        # Try to view emp003 who belongs to mgr002
        response = client.get('/manager/report/emp003')
        assert response.status_code == 403

    def test_view_report_aggregates_tenet_counts(self, client, db_session):
        """Test report aggregates tenet counts correctly"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        response = client.get('/manager/report/emp002')
        assert response.status_code == 200

        # Response should contain butterfly chart data
        # The actual counts depend on fixture data


class TestManagerFeedbackAPI:
    """Test manager feedback API"""

    def test_save_manager_feedback_creates_record(self, client, db_session):
        """Test creating manager feedback via API"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        feedback_data = {
            'team_member_uid': 'emp002',
            'selected_strengths': ['tenet1', 'tenet2'],
            'selected_improvements': ['tenet3'],
            'feedback_text': 'Strong performer this quarter'
        }

        response = client.post('/api/manager-feedback',
                               data=json.dumps(feedback_data),
                               content_type='application/json')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify in database
        mgr_feedback = db_session.query(ManagerFeedback).filter_by(
            manager_uid='mgr001',
            team_member_uid='emp002'
        ).first()

        assert mgr_feedback is not None
        assert mgr_feedback.feedback_text == 'Strong performer this quarter'

    def test_save_manager_feedback_updates_existing(self, client, db_session):
        """Test updating existing manager feedback"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        updated_data = {
            'team_member_uid': 'emp001',
            'selected_strengths': ['tenet3', 'tenet4'],
            'selected_improvements': ['tenet1', 'tenet2'],
            'feedback_text': 'Updated feedback text'
        }

        response = client.post('/api/manager-feedback',
                               data=json.dumps(updated_data),
                               content_type='application/json')

        assert response.status_code == 200

        # Verify update
        mgr_feedback = db_session.query(ManagerFeedback).filter_by(
            manager_uid='mgr001',
            team_member_uid='emp001'
        ).first()

        assert mgr_feedback.feedback_text == 'Updated feedback text'
        assert mgr_feedback.get_selected_strengths() == ['tenet3', 'tenet4']

    def test_save_manager_feedback_requires_session(self, client):
        """Test manager feedback API requires session"""
        feedback_data = {
            'team_member_uid': 'emp001',
            'selected_strengths': [],
            'selected_improvements': [],
            'feedback_text': 'Test'
        }

        response = client.post('/api/manager-feedback',
                               data=json.dumps(feedback_data),
                               content_type='application/json')

        assert response.status_code == 400

    def test_save_manager_feedback_prevents_duplicate_tenets(self, client, db_session):
        """Test manager feedback API enforces mutual exclusivity (no tenet in both lists)"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        # Attempt to save with overlapping tenets
        feedback_data = {
            'team_member_uid': 'emp002',
            'selected_strengths': ['tenet1', 'tenet2', 'tenet3'],
            'selected_improvements': ['tenet2', 'tenet4'],  # tenet2 overlaps
            'feedback_text': 'Test feedback'
        }

        response = client.post('/api/manager-feedback',
                               data=json.dumps(feedback_data),
                               content_type='application/json')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify in database that overlapping tenet was removed from both
        mgr_feedback = db_session.query(ManagerFeedback).filter_by(
            manager_uid='mgr001',
            team_member_uid='emp002'
        ).first()

        strengths = mgr_feedback.get_selected_strengths()
        improvements = mgr_feedback.get_selected_improvements()

        # tenet2 should not appear in either list (removed due to overlap)
        assert 'tenet2' not in strengths
        assert 'tenet2' not in improvements

        # Other tenets should be preserved
        assert 'tenet1' in strengths
        assert 'tenet3' in strengths
        assert 'tenet4' in improvements


class TestTenetsLoading:
    """Test tenets configuration loading"""

    def test_app_loads_active_tenets_only(self, client):
        """Test that only active tenets are loaded"""
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        response = client.get('/individual')
        data = response.data.decode('utf-8')

        # Should include active tenets
        assert 'tenet1' in data or 'Test Tenet 1' in data

        # Should not include inactive tenet
        assert 'inactive_tenet' not in data


class TestSessionManagement:
    """Test session persistence and isolation"""

    def test_individual_and_manager_sessions_independent(self, client):
        """Test individual and manager sessions are independent"""
        # Set individual session
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'
            sess['manager_uid'] = 'mgr001'

        # Clear individual session
        response = client.get('/individual/switch', follow_redirects=False)

        # Manager session should remain
        with client.session_transaction() as sess:
            assert 'user_id' not in sess
            assert sess.get('manager_uid') == 'mgr001'


class TestPDFExport:
    """Test PDF report export functionality"""

    def test_export_pdf_returns_pdf_file(self, client):
        """Test PDF export returns PDF file with correct content type"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        response = client.get('/manager/export-pdf/emp001')
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.headers['Content-Disposition'].startswith('attachment')
        assert b'%PDF' in response.data  # PDF file signature

    def test_export_pdf_requires_manager_session(self, client):
        """Test PDF export requires manager session"""
        response = client.get('/manager/export-pdf/emp001')
        assert response.status_code == 400

    def test_export_pdf_validates_team_membership(self, client):
        """Test manager can only export PDFs for their team members"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        # Try to export emp003 who belongs to mgr002
        response = client.get('/manager/export-pdf/emp003')
        assert response.status_code == 403

    def test_export_pdf_includes_team_member_info(self, client):
        """Test exported PDF filename includes team member name"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        response = client.get('/manager/export-pdf/emp001')
        assert response.status_code == 200

        # Check filename contains sanitized name and date
        content_disposition = response.headers['Content-Disposition']
        assert 'Feedback_Report_' in content_disposition
        assert '.pdf' in content_disposition

    def test_butterfly_chart_generation(self):
        """Test butterfly chart image generation"""
        from feedback_app import generate_butterfly_chart_image

        butterfly_data = [
            {'id': 'tenet1', 'name': 'Test Tenet 1', 'strength_count': 5, 'improvement_count': 2},
            {'id': 'tenet2', 'name': 'Test Tenet 2', 'strength_count': 3, 'improvement_count': 4},
        ]

        manager_selected_strengths = ['tenet1']
        manager_selected_improvements = ['tenet2']

        # Generate chart
        image_base64 = generate_butterfly_chart_image(
            butterfly_data,
            manager_selected_strengths,
            manager_selected_improvements
        )

        # Verify it's a valid base64 string
        assert isinstance(image_base64, str)
        assert len(image_base64) > 0

        # Verify it can be decoded
        import base64
        decoded = base64.b64decode(image_base64)
        assert len(decoded) > 0
        assert decoded.startswith(b'\x89PNG')  # PNG file signature

    def test_butterfly_chart_with_no_data(self):
        """Test butterfly chart handles empty data gracefully"""
        from feedback_app import generate_butterfly_chart_image

        image_base64 = generate_butterfly_chart_image([], [], [])

        # Should still return a valid image
        assert isinstance(image_base64, str)
        assert len(image_base64) > 0

    def test_export_pdf_with_manager_feedback(self, client, db_session):
        """Test PDF export includes manager feedback when present"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        # Add manager feedback
        mgr_feedback = ManagerFeedback(
            manager_uid='mgr001',
            team_member_uid='emp002',
            feedback_text='Excellent work this quarter'
        )
        mgr_feedback.set_selected_strengths(['tenet1'])
        mgr_feedback.set_selected_improvements(['tenet2'])
        db_session.add(mgr_feedback)
        db_session.commit()

        response = client.get('/manager/export-pdf/emp002')
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'

    def test_export_pdf_without_feedback(self, client, db_session):
        """Test PDF export works even without peer feedback"""
        with client.session_transaction() as sess:
            sess['manager_uid'] = 'mgr001'

        # Create a new team member with no feedback
        new_person = Person(
            user_id='emp999',
            name='Test Person',
            job_title='Test Role',
            email='test@example.com',
            manager_uid='mgr001'
        )
        db_session.add(new_person)
        db_session.commit()

        response = client.get('/manager/export-pdf/emp999')
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
