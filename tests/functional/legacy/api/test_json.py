# SPDX-License-Identifier: Apache-2.0

from tests.common.db.packaging import ReleaseFactory


def test_json_project(webtest):
    """
    Testing JSON API for basic structure

    Exercises `warehouse.legacy.api.json.json_project` with full web stack
    """
    release = ReleaseFactory.create()

    resp = webtest.get(f"/pypi/{release.project.normalized_name}/json")

    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "max-age=900, public"
    assert resp.headers["Content-Type"] == "application/json"
    assert resp.headers["X-PyPI-Last-Serial"] == str(release.project.last_serial)
    # How many database calls are needed to satisfy the data
    assert len(webtest.query_recorder.queries) == 7
