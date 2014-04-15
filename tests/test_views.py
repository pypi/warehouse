# Copyright 2013 Donald Stufft
#
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

from warehouse import views
from warehouse.views import index


def test_index(monkeypatch, warehouse_app):
    project_count = pretend.stub()
    download_count = pretend.stub()
    updated = pretend.stub()

    warehouse_app.warehouse_config = pretend.stub(
        cache=pretend.stub(browser=False, varnish=False),
    )
    warehouse_app.db = pretend.stub(
        packaging=pretend.stub(
            get_project_count=pretend.call_recorder(
                lambda: project_count,
            ),
            get_download_count=pretend.call_recorder(
                lambda: download_count,
            ),
            get_recently_updated=pretend.call_recorder(lambda: updated),
        ),
    )
    response = pretend.stub(
        status_code=200,
        headers={},
        cache_control=pretend.stub(),
        surrogate_control=pretend.stub(),
    )
    render_template = pretend.call_recorder(lambda *a, **kw: response)

    monkeypatch.setattr(views, "render_template", render_template)

    with warehouse_app.test_request_context('/'):
        resp = index()

    assert resp is response

    packaging = warehouse_app.db.packaging
    assert packaging.get_project_count.calls == [pretend.call()]
    assert packaging.get_download_count.calls == [pretend.call()]
    assert packaging.get_recently_updated.calls == [pretend.call()]
    assert render_template.calls == [
        pretend.call(
            "index.html",
            project_count=project_count,
            download_count=download_count,
            recently_updated=updated,
        ),
    ]
