# SPDX-License-Identifier: Apache-2.0
"""Tests for RFC 9457 (Problem Details for HTTP APIs) support."""

import json

import pretend
import pytest

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPNotFound,
)

from warehouse.rfc9457 import (
    RFC9457_CONTENT_TYPE,
    ProblemDetails,
    accepts_problem_json,
    problem_details_from_exception,
)


class TestProblemDetails:
    def test_to_dict_with_all_fields(self):
        """Test converting ProblemDetails to dict with all fields."""
        problem = ProblemDetails(
            status=404,
            title="Not Found",
            detail="The requested resource was not found",
            type="https://example.com/problems/not-found",
            instance="/simple/nonexistent-package",
            extensions={"retry_after": 60},
        )

        result = problem.to_dict()

        assert result["status"] == 404
        assert result["title"] == "Not Found"
        assert result["detail"] == "The requested resource was not found"
        assert result["type"] == "https://example.com/problems/not-found"
        assert result["instance"] == "/simple/nonexistent-package"
        assert result["retry_after"] == 60

    def test_to_dict_minimal_fields(self):
        """Test converting ProblemDetails with only required fields."""
        problem = ProblemDetails(
            status=500,
            title="Internal Server Error",
        )

        result = problem.to_dict()

        assert result["status"] == 500
        assert result["title"] == "Internal Server Error"
        assert "detail" not in result
        assert "type" not in result  # about:blank is default, not included
        assert "instance" not in result

    def test_to_dict_omits_about_blank(self):
        """Test that default type 'about:blank' is omitted from output."""
        problem = ProblemDetails(
            status=400,
            title="Bad Request",
            type="about:blank",
        )

        result = problem.to_dict()

        assert "type" not in result

    def test_to_json(self):
        """Test JSON serialization."""
        problem = ProblemDetails(
            status=403,
            title="Forbidden",
            detail="Access denied",
        )

        json_str = problem.to_json()
        data = json.loads(json_str)

        assert data["status"] == 403
        assert data["title"] == "Forbidden"
        assert data["detail"] == "Access denied"

    def test_string_representation(self):
        """Test human-readable string representation."""
        problem = ProblemDetails(
            status=404,
            title="Not Found",
            detail="The package 'test-package' does not exist",
        )

        str_repr = str(problem)

        assert "Not Found" in str_repr
        assert "404" in str_repr
        assert "test-package" in str_repr

    def test_string_representation_minimal(self):
        """Test string representation with only title."""
        problem = ProblemDetails(
            status=500,
            title="Error",
        )

        str_repr = str(problem)

        assert "Error" in str_repr
        assert "500" in str_repr

    def test_string_representation_empty(self):
        """Test string representation when fields are empty."""
        problem = ProblemDetails(
            status=0,
            title="",
        )

        str_repr = str(problem)

        assert str_repr == "Unknown problem"


class TestProblemDetailsFromException:
    def test_from_http_not_found(self):
        """Test converting HTTPNotFound exception."""
        exc = HTTPNotFound()

        problem = problem_details_from_exception(exc)

        assert problem.status == 404
        assert problem.title == "Not Found"
        assert problem.detail is not None

    def test_from_http_forbidden(self):
        """Test converting HTTPForbidden exception."""
        exc = HTTPForbidden()

        problem = problem_details_from_exception(exc)

        assert problem.status == 403
        assert problem.title == "Forbidden"

    def test_from_http_internal_server_error(self):
        """Test converting HTTPInternalServerError exception."""
        exc = HTTPInternalServerError()

        problem = problem_details_from_exception(exc)

        assert problem.status == 500
        assert problem.title == "Internal Server Error"

    def test_with_custom_detail(self):
        """Test providing custom detail message."""
        exc = HTTPNotFound()
        custom_detail = "The package 'my-package' was not found in the index"

        problem = problem_details_from_exception(exc, detail=custom_detail)

        assert problem.status == 404
        assert problem.detail == custom_detail

    def test_with_extensions(self):
        """Test adding extension members."""
        exc = HTTPNotFound()

        problem = problem_details_from_exception(
            exc, package_name="test-pkg", repository="pypi"
        )

        assert problem.extensions["package_name"] == "test-pkg"
        assert problem.extensions["repository"] == "pypi"

    def test_uses_exception_explanation(self):
        """Test that exception's explanation is used as detail."""
        exc = HTTPBadRequest(explanation="Invalid package name format")

        problem = problem_details_from_exception(exc)

        assert problem.status == 400
        assert problem.detail == "Invalid package name format"


class TestAcceptsProblemJson:
    def test_accepts_problem_json(self):
        """Test detection of application/problem+json in Accept header."""
        request = pretend.stub(
            accept=pretend.stub(
                acceptable_offers=pretend.call_recorder(
                    lambda offers: [(RFC9457_CONTENT_TYPE, 1.0)]
                )
            )
        )

        result = accepts_problem_json(request)

        assert result is True
        assert request.accept.acceptable_offers.calls == [
            pretend.call([RFC9457_CONTENT_TYPE])
        ]

    def test_does_not_accept_problem_json(self):
        """Test when client doesn't accept application/problem+json."""
        request = pretend.stub(
            accept=pretend.stub(acceptable_offers=pretend.call_recorder(lambda offers: []))
        )

        result = accepts_problem_json(request)

        assert result is False

    def test_accepts_with_quality_value(self):
        """Test acceptance with quality value."""
        request = pretend.stub(
            accept=pretend.stub(
                acceptable_offers=pretend.call_recorder(
                    lambda offers: [(RFC9457_CONTENT_TYPE, 0.8)]
                )
            )
        )

        result = accepts_problem_json(request)

        assert result is True

    def test_accepts_with_multiple_types(self):
        """Test when multiple content types are acceptable."""
        request = pretend.stub(
            accept=pretend.stub(
                acceptable_offers=pretend.call_recorder(
                    lambda offers: [
                        ("text/html", 1.0),
                        (RFC9457_CONTENT_TYPE, 0.9),
                    ]
                )
            )
        )

        result = accepts_problem_json(request)

        assert result is True