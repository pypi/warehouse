# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPBadRequest

from warehouse.api.problems import problem


def test_problem():
    resp = problem(
        HTTPBadRequest,
        "Missing required fields: name",
        headers={"Retry-After": "60"},
        missing=["name"],
        detail="ignored",
        status=999,
    )

    assert isinstance(resp, HTTPBadRequest)
    assert resp.content_type == "application/problem+json"
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["Retry-After"] == "60"
    # Extension members can't replace the standard ones.
    assert resp.json_body == {
        "type": "about:blank",
        "title": "Bad Request",
        "status": 400,
        "detail": "Missing required fields: name",
        "missing": ["name"],
    }
