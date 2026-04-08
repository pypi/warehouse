# Functional Tests

This directory contains **functional tests** for the Warehouse application.

## What Are Functional Tests?

Functional tests simulate real end-user interactions with PyPI. They test the application from the outside-in, verifying that features work correctly when accessed through the web interface.

## Guidelines

### Do

- **Use the `webtest` fixture** to simulate HTTP requests and responses
- **Test user workflows** (e.g., login → navigate to project → upload package)
- **Use factories** from `tests/common/db/*.py` to create test data
- **Use fixtures** from `tests/conftest.py` for common setup (e.g., `db_request`, `db_session`)
- **Test with database state** - functional tests are meant to interact with the database

### Don't

- **Mocking/patching** with `monkeypatch`, `mocker`, or `pretend` - these belong in unit tests
- **Testing internal implementation details** - focus on user-facing behavior
- **Direct model manipulation** without going through views/forms when testing user flows

## Example Pattern

```python
from tests.common.db.accounts import UserFactory
from tests.common.db.packaging import ProjectFactory

def test_user_can_view_project(webtest):
    """Test that a user can view a project page."""
    # Arrange: Create test data
    user = UserFactory.create()
    project = ProjectFactory.create(name="my-package")

    # Act: Simulate user request
    response = webtest.get(f"/project/my-package/")

    # Assert: Verify response
    assert response.status_code == 200
    assert "my-package" in response.text
```

## References

- [WebTest Documentation](https://docs.pylonsproject.org/projects/webtest/)
- Custom `webtest` fixture: `tests/conftest.py`
- Test factories: `tests/common/db/*.py`
