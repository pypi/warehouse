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

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPBadRequest

from warehouse import redirects


class TestRedirectView:

    def test_redirect_view(self):
        target = "/{wat}/{_request.method}"
        view = redirects.redirect_view_factory(target)

        request = pretend.stub(method="GET", matchdict={"wat": "the-thing"})
        resp = view(request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/the-thing/GET"

    def test_redirect_view_raises_for_invalid_chars(self):
        target = "/{wat}/{_request.method}"
        view = redirects.redirect_view_factory(target)
        request = pretend.stub(method="GET", matchdict={"wat": "the-thing\n"})

        with pytest.raises(HTTPBadRequest,
                           match="URL may not contain control characters"):
            view(request)


def test_add_redirect(monkeypatch):
    rview = pretend.stub()
    rview_factory = pretend.call_recorder(lambda target, redirect: rview)
    monkeypatch.setattr(redirects, "redirect_view_factory", rview_factory)

    config = pretend.stub(
        add_route=pretend.call_recorder(lambda name, route, **kw: None),
        add_view=pretend.call_recorder(lambda view, route_name: None),
    )

    source = "/the/{thing}/"
    target = "/other/{thing}/"
    redirect = pretend.stub()
    kwargs = {
        'redirect': redirect,
    }

    redirects.add_redirect(config, source, target, **kwargs)

    assert config.add_route.calls == [
        pretend.call(
            "warehouse.redirects." + source + str(kwargs), source, **kwargs
        ),
    ]
    assert config.add_view.calls == [
        pretend.call(
            rview, route_name="warehouse.redirects." + source + str(kwargs)
        ),
    ]
    assert rview_factory.calls == [pretend.call(target, redirect=redirect)]


def test_includeme():
    config = pretend.stub(
        add_directive=pretend.call_recorder(lambda n, fn, action_wrap: None),
    )
    redirects.includeme(config)
    assert config.add_directive.calls == [
        pretend.call(
            "add_redirect",
            redirects.add_redirect,
            action_wrap=False,
        ),
    ]
