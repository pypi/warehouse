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

from warehouse.forklift import includeme


@pytest.mark.parametrize("forklift", [None, "upload.pypi.io"])
def test_includeme(forklift):
    settings = {}
    if forklift:
        settings["forklift.domain"] = forklift

    config = pretend.stub(
        get_settings=lambda: settings,
        include=pretend.call_recorder(lambda n: None),
        add_legacy_action_route=pretend.call_recorder(lambda *a, **k: None),
        add_template_view=pretend.call_recorder(lambda *a, **kw: None),
    )

    includeme(config)

    config.include.calls == [pretend.call(".action_routing")]
    config.add_legacy_action_route.calls == [
        pretend.call(
            "forklift.legacy.file_upload",
            "file_upload",
            domain=forklift,
        ),
        pretend.call("forklift.legacy.submit", "submit", domain=forklift),
        pretend.call(
            "forklift.legacy.submit_pkg_info",
            "submit_pkg_info",
            domain=forklift,
        ),
        pretend.call(
            "forklift.legacy.doc_upload",
            "doc_upload",
            domain=forklift,
        ),
    ]
    if forklift:
        config.add_template_view.calls == [
            pretend.call(
                "forklift.index",
                "/",
                "upload.html",
                route_kw={"domain": forklift},
            ),
        ]
    else:
        config.add_template_view.calls == []
