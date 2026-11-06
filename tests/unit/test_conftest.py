# SPDX-License-Identifier: Apache-2.0

from unittest import mock

import pytest

from webob.multidict import MultiDict, NestedMultiDict, NoVars

from tests import conftest
from tests.common.forms import FormRequest, file_part


def test_guard_mock_sentinels_reports_and_restores_mutations():
    first = mock.sentinel.guard_test_first
    first.leaked = object()

    guard = conftest.guard_mock_sentinels.__wrapped__()
    next(guard)

    second = mock.sentinel.guard_test_second
    second.also_leaked = object()

    with pytest.raises(AssertionError) as exc_info:
        next(guard)

    assert "mock.sentinel.guard_test_first" in str(exc_info.value)
    assert "mock.sentinel.guard_test_second" in str(exc_info.value)
    assert vars(first) == {"name": "guard_test_first"}
    assert vars(second) == {"name": "guard_test_second"}


@pytest.mark.parametrize(
    "write",
    [
        lambda request: setattr(request, "POST", {"id": 1}),
        lambda request: setattr(request, "GET", {"id": 1}),
        lambda request: setattr(request, "params", {"id": 1}),
        lambda request: request.POST.__setitem__("id", 1),
        lambda request: request.POST.add("id", 1),
        lambda request: request.POST.update({"id": 1}),
        lambda request: request.params.extend({"id": 1}),
        lambda request: setattr(
            request, "params", NestedMultiDict(MultiDict({"id": 1}))
        ),
        lambda request: FormRequest(POST={"id": 1}),
    ],
    ids=[
        "set-post",
        "set-get",
        "set-params",
        "setitem",
        "add",
        "update",
        "extend",
        "nested",
        "post-kwarg",
    ],
)
def test_pyramid_request_rejects_non_form_values(pyramid_request, write):
    with pytest.raises(TypeError, match="form value for 'id' is int"):
        write(pyramid_request)


def test_pyramid_request_accepts_form_values(pyramid_request):
    pyramid_request.POST["name"] = "value"
    upload = file_part()
    pyramid_request.POST["upload"] = upload
    pyramid_request.POST["empty"] = b""
    pyramid_request.POST["unnamed"] = b"body"

    assert pyramid_request.GET is pyramid_request.POST is pyramid_request.params
    assert pyramid_request.POST.getall("upload") == [upload]


def test_pyramid_request_keeps_an_assigned_multidict(pyramid_request):
    posted = MultiDict()
    pyramid_request.POST = posted
    posted["name"] = "value"

    assert pyramid_request.POST is posted
    assert pyramid_request.POST["name"] == "value"
    with pytest.raises(TypeError, match="form value for 'id' is int"):
        posted["id"] = 1


def test_form_request_keeps_an_empty_multidict():
    params = MultiDict()
    request = FormRequest(params)

    assert request.params is params


@pytest.mark.parametrize(
    "values", [NoVars(), NestedMultiDict(MultiDict(), MultiDict())]
)
def test_pyramid_request_keeps_read_only_values(pyramid_request, values):
    pyramid_request.POST = values

    assert pyramid_request.POST is values


def test_pyramid_request_guards_a_nested_multidict(pyramid_request):
    inner = MultiDict()
    pyramid_request.params = NestedMultiDict(inner)

    with pytest.raises(TypeError, match="form value for 'id' is int"):
        inner["id"] = 1
