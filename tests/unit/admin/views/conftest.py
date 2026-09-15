# SPDX-License-Identifier: Apache-2.0

import pytest


def _fake_route_path(name, **kw):
    """Predictable route_path stub covering the routes the admin views use."""
    if name == "admin.user.detail":
        return f"/admin/users/{kw['username']}/"
    if name == "admin.project.detail":
        return f"/admin/projects/{kw['project_name']}/"
    if name == "admin.organization_application.detail":
        return f"/admin/organization_applications/{kw['organization_application_id']}/"
    raise AssertionError(f"unexpected route: {name}")  # pragma: no cover


@pytest.fixture
def route_request(db_request):
    """db_request with a predictable route_path for JSON payload tests."""
    db_request.route_path = _fake_route_path
    return db_request
