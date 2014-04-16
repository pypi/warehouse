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

from warehouse.views import index


def test_index(app):
    project_count = pretend.stub()
    download_count = pretend.stub()
    updated = pretend.stub()

    app.db = pretend.stub(
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

    request = pretend.stub()

    resp = index(app, request)

    assert resp.response.template.name == "index.html"
    assert resp.response.context == {
        "project_count": project_count,
        "download_count": download_count,
        "recently_updated": updated,
    }
    assert app.db.packaging.get_project_count.calls == [pretend.call()]
    assert app.db.packaging.get_download_count.calls == [pretend.call()]
    assert app.db.packaging.get_recently_updated.calls == [pretend.call()]
