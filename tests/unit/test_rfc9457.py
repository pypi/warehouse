# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPNotFound,
)

from warehouse.rfc9457 import (
    ProblemDetails,
    problem_details_from_exception,
)


class TestProblemDetails:
    def test_to_dict_with_all_fields(self):
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

    @pytest.mark.parametrize(
        "forbidden_key",
        ["status", "title", "detail", "type", "instance"],
    )
    def test_extensions_cannot_override_required_fields(self, forbidden_key):
        problem = ProblemDetails(
            status=400,
            title="Bad Request",
            extensions={forbidden_key: "should not be allowed"},
        )

        with pytest.raises(
            ValueError, match="Extensions cannot override required RFC 9457 fields"
        ):
            problem.to_dict()

    def test_to_dict_minimal_fields(self):
        problem = ProblemDetails(
            status=500,
            title="Internal Server Error",
            type="about:blank",
        )

        result = problem.to_dict()

        assert result["status"] == 500
        assert result["title"] == "Internal Server Error"
        assert "detail" not in result
        assert "type" not in result
        assert "instance" not in result

    def test_to_json(self):
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

    def test_to_json_with_extensions(self):
        problem = ProblemDetails(
            status=429,
            title="Too Many Requests",
            extensions={"retry_after": 60, "limit": 100},
        )

        json_str = problem.to_json()
        data = json.loads(json_str)

        assert data["status"] == 429
        assert data["retry_after"] == 60
        assert data["limit"] == 100

    def test_string_representation_empty(self):
        problem = ProblemDetails(
            status=0,
            title="",
        )

        str_repr = str(problem)

        assert str_repr == "Unknown problem"


class TestProblemDetailsFromException:
    def test_from_http_not_found(self):
        exc = HTTPNotFound()

        problem = problem_details_from_exception(exc)

        assert problem.status == 404
        assert problem.title == "Not Found"
        assert problem.detail is not None
        assert problem.type == "about:blank"

    def test_from_http_forbidden(self):
        exc = HTTPForbidden()

        problem = problem_details_from_exception(exc)

        assert problem.status == 403
        assert problem.title == "Forbidden"
        assert problem.type == "about:blank"

    def test_from_http_internal_server_error(self):
        exc = HTTPInternalServerError()

        problem = problem_details_from_exception(exc)

        assert problem.status == 500
        assert problem.title == "Internal Server Error"

    def test_with_custom_detail(self):
        exc = HTTPNotFound()
        custom_detail = "The package 'my-package' was not found in the index"

        problem = problem_details_from_exception(exc, detail=custom_detail)

        assert problem.status == 404
        assert problem.detail == custom_detail

    def test_with_extensions(self):
        exc = HTTPNotFound()

        problem = problem_details_from_exception(
            exc, package_name="test-pkg", repository="pypi"
        )

        assert problem.extensions["package_name"] == "test-pkg"
        assert problem.extensions["repository"] == "pypi"

    def test_uses_exception_explanation(self):
        exc = HTTPBadRequest(explanation="Invalid package name format")

        problem = problem_details_from_exception(exc)

        assert problem.status == 400
        assert problem.detail == "Invalid package name format"

    def test_custom_detail_overrides_exception_explanation(self):
        exc = HTTPBadRequest(explanation="Default explanation")
        custom_detail = "Custom detail message"

        problem = problem_details_from_exception(exc, detail=custom_detail)

        assert problem.detail == custom_detail
        assert problem.detail != "Default explanation"

    @pytest.mark.parametrize(
        ("exc_class", "expected_status"),
        [
            (HTTPBadRequest, 400),
            (HTTPForbidden, 403),
            (HTTPInternalServerError, 500),
        ],
    )
    def test_various_exception_types(self, exc_class, expected_status):
        exc = exc_class()
        problem = problem_details_from_exception(exc)

        assert problem.status == expected_status
        assert isinstance(problem.title, str)
        assert len(problem.title) > 0

    @pytest.mark.parametrize(
        ("exc_class", "expected_status", "expected_title"),
        [
            (HTTPForbidden, 403, "Forbidden"),
            (HTTPInternalServerError, 500, "Internal Server Error"),
        ],
    )
    def test_uses_standard_http_status_phrases(
        self, exc_class, expected_status, expected_title
    ):
        exc = exc_class()
        problem = problem_details_from_exception(exc)

        assert problem.status == expected_status
        assert problem.title == expected_title
        assert problem.type == "about:blank"

    def test_custom_type_uses_exception_title(self):
        exc = HTTPNotFound()
        custom_type = "https://pypi.org/errors/package-not-found"

        problem = problem_details_from_exception(exc, type=custom_type)

        assert problem.status == 404
        assert problem.type == custom_type
        assert problem.title == exc.title
