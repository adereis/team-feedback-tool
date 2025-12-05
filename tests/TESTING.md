# Testing Guide - Team Feedback Tool

Comprehensive testing documentation for the Team Feedback Tool project.

## Overview

This project uses **pytest** for testing with three main test suites:
- **test_models.py**: Unit tests for database models (Person, Feedback, ManagerFeedback)
- **test_app.py**: Integration tests for Flask routes and API endpoints
- **test_integration.py**: End-to-end workflow tests

## Quick Start

### Run All Tests
```bash
pytest
```

### Run Specific Test File
```bash
pytest test_models.py
pytest test_app.py
pytest test_integration.py
```

### Run Specific Test Class
```bash
pytest test_models.py::TestPersonModel
pytest test_app.py::TestFeedbackAPI
```

### Run Specific Test
```bash
pytest test_models.py::TestPersonModel::test_person_creation_with_all_fields
```

### Run with Verbose Output
```bash
pytest -v
```

### Run with Coverage Report
```bash
pytest --cov=feedback_app --cov=feedback_models --cov-report=html
```

## Test Structure

### conftest.py
Contains shared pytest fixtures used across all tests:

- **test_db**: Creates temporary SQLite database with sample data
- **test_tenets_file**: Creates temporary tenets configuration
- **app**: Flask app configured for testing
- **client**: Test client for making HTTP requests
- **db_session**: Direct database session for test assertions
- **sample_csv_feedback**: Sample CSV data for import tests

### test_models.py
Unit tests for database models focusing on:

- Database initialization and session creation
- Person model CRUD operations and relationships
- Feedback model with JSON serialization of tenets
- ManagerFeedback model functionality
- Model relationships and foreign keys
- to_dict() serialization methods

**Example tests:**
- `test_person_creation_with_all_fields`
- `test_feedback_strengths_json_serialization`
- `test_manager_feedback_to_dict_conversion`

### test_app.py
Integration tests for Flask routes and APIs:

- Individual workflow routes (/individual, /individual/<user_id>)
- Manager workflow routes (/manager, /manager/<manager_uid>)
- API endpoints for feedback submission and deletion
- CSV import/export functionality
- Session management
- Input validation and error handling

**Example tests:**
- `test_save_feedback_new_creates_record`
- `test_export_csv_downloads_file`
- `test_manager_dashboard_shows_team_members`

### test_integration.py
End-to-end workflow tests covering:

- Complete individual feedback workflow
- Complete manager workflow
- Multi-user scenarios
- Data consistency across operations
- Cross-workflow integration
- Edge cases and boundary conditions

**Example tests:**
- `test_complete_individual_workflow`
- `test_individual_export_and_manager_import`
- `test_external_user_not_in_database`

## Test Data

Tests use **isolated temporary databases** created for each test session. Sample data includes:

### People
- **mgr001**: Alice Manager (Engineering Manager)
- **mgr002**: Bob Manager (Senior Manager)
- **emp001**: Charlie Developer (reports to mgr001)
- **emp002**: Diana Developer (reports to mgr001)
- **emp003**: Eve Engineer (reports to mgr002)

### Tenets
- **tenet1-4**: Test tenets (active)
- **inactive_tenet**: Inactive tenet (should not appear)

### Pre-existing Feedback
- emp001 → emp002 (from fixture)
- emp002 → emp001 (from fixture)
- mgr001 → emp001 (manager feedback from fixture)

## Writing New Tests

### Test Naming Convention
Follow the pattern: `test_[feature]_[scenario]_[expected_result]`

```python
def test_save_feedback_validates_strengths_count(self, client):
    """Test API validates exactly 3 strengths required"""
    # Test implementation
```

### Test Independence
Each test must be **completely independent** with no shared state:

```python
# GOOD - Test creates its own data
def test_create_feedback(self, client, db_session):
    feedback = Feedback(from_user_id='test', to_user_id='test2')
    db_session.add(feedback)
    db_session.commit()
    # assertions

# BAD - Test relies on data from another test
def test_update_feedback(self, client, db_session):
    # Assumes feedback from previous test exists
    feedback = db_session.query(Feedback).first()
```

### Using Fixtures
Leverage pytest fixtures for common setup:

```python
def test_with_session(self, client):
    """Test using client fixture"""
    with client.session_transaction() as sess:
        sess['user_id'] = 'emp001'

    response = client.get('/individual')
    assert response.status_code == 200

def test_with_db(self, db_session):
    """Test using db_session fixture"""
    person = db_session.query(Person).filter_by(user_id='emp001').first()
    assert person.name == 'Charlie Developer'
```

### Testing API Endpoints
Use the test client for API calls:

```python
def test_api_endpoint(self, client):
    data = {'key': 'value'}
    response = client.post('/api/endpoint',
                          data=json.dumps(data),
                          content_type='application/json')

    assert response.status_code == 200
    result = json.loads(response.data)
    assert result['success'] is True
```

### Testing Session Management
Use session_transaction context manager:

```python
def test_session(self, client):
    # Set session
    with client.session_transaction() as sess:
        sess['user_id'] = 'test_user'

    # Make request (session persists)
    response = client.get('/some-route')

    # Check session
    with client.session_transaction() as sess:
        assert sess.get('user_id') == 'test_user'
```

## Continuous Integration

### Pre-commit Hook
Consider adding a pre-commit hook to run tests:

```bash
#!/bin/sh
pytest --tb=short
```

### Running Tests Before Commits
Always run the test suite before committing:

```bash
pytest && git commit -m "Your message"
```

## Troubleshooting

### Tests Fail Due to Database Lock
If you see SQLite database lock errors:
- Ensure all sessions are properly closed in tests
- Check that fixtures clean up after themselves

### Import Errors
If you see import errors:
```bash
# Ensure you're in the project directory
cd /path/to/team-feedback-tool

# Run pytest
pytest
```

### Fixture Not Found
If pytest can't find a fixture:
- Ensure conftest.py is in the same directory
- Check fixture name spelling
- Verify fixture is properly decorated with @pytest.fixture

### Session Issues
If session-related tests fail:
- Use `client.session_transaction()` context manager
- Remember sessions persist across requests in the same test
- Clear sessions with appropriate routes (/individual/switch, /manager/switch)

## Test Coverage Goals

Aim for:
- **Models**: 95%+ coverage (critical business logic)
- **Routes**: 85%+ coverage (all major paths tested)
- **Integration**: All critical workflows covered

## Best Practices

1. **One assertion focus per test**: Each test should verify one specific behavior
2. **Descriptive test names**: Names should explain what's being tested
3. **Arrange-Act-Assert**: Structure tests clearly
4. **Use fixtures**: Don't repeat setup code
5. **Test edge cases**: Don't just test happy paths
6. **Clean test data**: Use temporary databases, never production data
7. **Independent tests**: Never rely on test execution order

## Example Test Workflow

```python
class TestFeature:
    """Test description of feature"""

    def test_feature_happy_path(self, client, db_session):
        """Test feature works in normal conditions"""
        # Arrange: Set up test data
        with client.session_transaction() as sess:
            sess['user_id'] = 'emp001'

        # Act: Perform the action
        response = client.get('/some-route')

        # Assert: Verify results
        assert response.status_code == 200
        assert b'expected content' in response.data

    def test_feature_error_handling(self, client):
        """Test feature handles errors correctly"""
        # Arrange: Set up error condition
        # (no session set)

        # Act: Perform action
        response = client.get('/some-route')

        # Assert: Verify error handling
        assert response.status_code == 400

    def test_feature_edge_case(self, client, db_session):
        """Test feature handles edge case"""
        # Test edge case implementation
```

## Running Specific Test Categories

Tests can be marked and run by category:

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

To add markers to tests:
```python
@pytest.mark.unit
def test_something(self):
    pass

@pytest.mark.slow
def test_slow_operation(self):
    pass
```

## Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Flask Testing Documentation](https://flask.palletsprojects.com/en/stable/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/latest/core/testing.html)
