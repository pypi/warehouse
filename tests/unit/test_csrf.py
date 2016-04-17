# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pretend
import pytest

from pyramid.exceptions import BadCSRFToken
from pyramid.httpexceptions import HTTPMethodNotAllowed
from pyramid.viewderivers import INGRESS, secured_view

from warehouse import csrf


class TestCSRFView:

    def test_defaults_to_method_not_allowed_unsafe(self):
        def view(context, request):
            assert False, "View should never be called"

        info = pretend.stub(options={})
        wrapped_view = csrf.csrf_view(view, info)
        context = pretend.stub()
        request = pretend.stub(method="POST")

        with pytest.raises(HTTPMethodNotAllowed):
            wrapped_view(context, request)

    def test_defaults_to_allowing_safe_methods(self):
        response = pretend.stub()

        def view(context, request):
            return response

        info = pretend.stub(options={})
        wrapped_view = csrf.csrf_view(view, info)
        context = pretend.stub()
        request = pretend.stub(method="GET")

        assert wrapped_view(context, request) is response

    def test_requires_csrf_true_allows_safe(self):
        response = pretend.stub()

        def view(context, request):
            return response

        info = pretend.stub(options={"require_csrf": True})
        wrapped_view = csrf.csrf_view(view, info)
        context = pretend.stub()
        request = pretend.stub(method="GET")

        assert wrapped_view(context, request) is response

    def test_requires_csrf_true_checks_csrf(self):
        def view(context, request):
            assert False, "View should never be called"

        info = pretend.stub(options={"require_csrf": True})
        wrapped_view = csrf.csrf_view(view, info)
        context = pretend.stub()
        request = pretend.stub(
            method="POST",
            scheme="http",
            POST={},
            headers={},
            session=pretend.stub(get_csrf_token=lambda: "a csrf token"),
        )

        with pytest.raises(BadCSRFToken):
            wrapped_view(context, request)

    def test_requires_csrf_false_allows_any(self):
        response = pretend.stub()

        def view(context, request):
            return response

        info = pretend.stub(options={"require_csrf": False})
        wrapped_view = csrf.csrf_view(view, info)
        context = pretend.stub()
        request = pretend.stub(method="POST")

        assert wrapped_view(context, request) is response


def test_includeme():
    config = pretend.stub(
        add_view_deriver=pretend.call_recorder(lambda *args, **kw: None),
    )

    csrf.includeme(config)

    assert config.add_view_deriver.calls == [
        pretend.call(csrf.csrf_view, under=INGRESS, over="secured_view"),
        pretend.call(secured_view, under="csrf_view"),
    ]
