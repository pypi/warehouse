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

import pytest


@pytest.mark.parametrize("action", ["submit", "submit_pkg_info"])
def test_removed_upload_apis(webtest, action):
    resp = webtest.post("/legacy/?:action={}".format(action), status=410)
    assert resp.status == (
        "410 Project pre-registration is no longer required or supported, "
        "upload your files instead."
    )


def test_remove_doc_upload(webtest):
    resp = webtest.post("/legacy/?:action=doc_upload", status=410)
    assert resp.status == (
        "410 Uploading documentation is no longer supported, we recommend "
        "using https://readthedocs.org/."
    )


def test_doap(webtest):
    resp = webtest.get("/pypi?:action=doap&name=foo&version=1.0", status=410)
    assert resp.status == "410 DOAP is no longer supported."
