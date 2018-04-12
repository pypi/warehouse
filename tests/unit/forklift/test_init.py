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

from warehouse import forklift


@pytest.mark.parametrize("forklift_domain", [None, "upload.pypi.io"])
def test_includeme(forklift_domain, monkeypatch):
    settings = {}
    if forklift_domain:
        settings["forklift.domain"] = forklift_domain

    _help_url = pretend.stub()
    monkeypatch.setattr(forklift, '_help_url', _help_url)

    config = pretend.stub(
        get_settings=lambda: settings,
        include=pretend.call_recorder(lambda n: None),
        add_legacy_action_route=pretend.call_recorder(lambda *a, **k: None),
        add_template_view=pretend.call_recorder(lambda *a, **kw: None),
        add_request_method=pretend.call_recorder(lambda *a, **kw: None),
    )

    forklift.includeme(config)

    assert config.include.calls == [pretend.call(".action_routing")]
    assert config.add_legacy_action_route.calls == [
        pretend.call(
            "forklift.legacy.file_upload",
            "file_upload",
            domain=forklift_domain,
        ),
        pretend.call(
            "forklift.legacy.submit",
            "submit",
            domain=forklift_domain,
        ),
        pretend.call(
            "forklift.legacy.submit_pkg_info",
            "submit_pkg_info",
            domain=forklift_domain,
        ),
        pretend.call(
            "forklift.legacy.doc_upload",
            "doc_upload",
            domain=forklift_domain,
        ),
    ]
    assert config.add_request_method.calls == [
        pretend.call(_help_url, name='help_url'),
    ]
    if forklift_domain:
        assert config.add_template_view.calls == [
            pretend.call(
                "forklift.index",
                "/",
                "upload.html",
                route_kw={"domain": forklift_domain},
            ),
            pretend.call(
                'forklift.legacy.invalid_request',
                '/legacy/',
                'upload.html',
                route_kw={'domain': 'upload.pypi.io'},
            ),
        ]
    else:
        assert config.add_template_view.calls == []


def test_help_url():
    warehouse_domain = pretend.stub()
    result = pretend.stub()
    request = pretend.stub(
        route_url=pretend.call_recorder(lambda *a, **kw: result),
        registry=pretend.stub(
            settings={'warehouse.domain': warehouse_domain},
        ),
    )

    assert forklift._help_url(request, _anchor='foo') == result
    assert request.route_url.calls == [
        pretend.call('help', _host=warehouse_domain, _anchor='foo'),
    ]
