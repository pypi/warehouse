# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from warehouse.api import integrity


@pytest.mark.parametrize(
    ("accept", "expected"),
    [
        # Simple cases
        (
            "application/vnd.pypi.integrity.v1+json",
            integrity.MIME_PYPI_INTEGRITY_V1_JSON,
        ),
        ("application/json", integrity.MIME_APPLICATION_JSON),
        # No accept header means we give the user our first offer
        (None, integrity.MIME_PYPI_INTEGRITY_V1_JSON),
        # Accept header contains only things we don't offer
        ("text/xml", None),
        ("application/octet-stream", None),
        ("text/xml, application/octet-stream", None),
        # Accept header contains both things we offer and things we don't;
        # we pick our matching offer even if the q-value is lower
        (
            "text/xml, application/vnd.pypi.integrity.v1+json",
            integrity.MIME_PYPI_INTEGRITY_V1_JSON,
        ),
        (
            "application/vnd.pypi.integrity.v1+json; q=0.1, text/xml",
            integrity.MIME_PYPI_INTEGRITY_V1_JSON,
        ),
        # Accept header contains multiple things we offer with the same q-value;
        # we pick our preferred offer
        (
            "application/json, application/vnd.pypi.integrity.v1+json",
            integrity.MIME_PYPI_INTEGRITY_V1_JSON,
        ),
        (
            "application/vnd.pypi.integrity.v1+json; q=0.5, application/json; q=0.5",
            integrity.MIME_PYPI_INTEGRITY_V1_JSON,
        ),
        # Accept header contains multiple things we offer; we pick our
        # offer based on the q-value
        (
            "application/vnd.pypi.integrity.v1+json; q=0.1, application/json",
            integrity.MIME_APPLICATION_JSON,
        ),
    ],
)
def test_select_content_type(db_request, accept, expected):
    db_request.accept = accept

    assert integrity._select_content_type(db_request) == expected


# Backstop; can be removed/changed once this view supports HTML.
@pytest.mark.parametrize(
    "content_type",
    ["text/html", "application/vnd.pypi.integrity.v1+html"],
)
def test_provenance_for_file_bad_accept(db_request, content_type):
    db_request.accept = content_type
    response = integrity.provenance_for_file(pretend.stub(), db_request)
    assert response.status_code == 406
    assert response.json == {"message": "Request not acceptable"}


def test_provenance_for_file_accept_multiple(db_request, monkeypatch):
    db_request.accept = "text/html, application/vnd.pypi.integrity.v1+json; q=0.9"
    file = pretend.stub(provenance=None, filename="fake-1.2.3.tar.gz")

    response = integrity.provenance_for_file(file, db_request)
    assert response.status_code == 404
    assert response.json == {"message": "No provenance available for fake-1.2.3.tar.gz"}


def test_provenance_for_file_not_enabled(db_request, monkeypatch):
    monkeypatch.setattr(db_request, "flags", pretend.stub(enabled=lambda *a: True))

    response = integrity.provenance_for_file(pretend.stub(), db_request)
    assert response.status_code == 403
    assert response.json == {"message": "Attestations temporarily disabled"}


def test_provenance_for_file_not_present(db_request, monkeypatch):
    monkeypatch.setattr(db_request, "flags", pretend.stub(enabled=lambda *a: False))
    file = pretend.stub(provenance=None, filename="fake-1.2.3.tar.gz")

    response = integrity.provenance_for_file(file, db_request)
    assert response.status_code == 404
    assert response.json == {"message": "No provenance available for fake-1.2.3.tar.gz"}
