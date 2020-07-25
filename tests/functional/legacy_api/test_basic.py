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


def test_incorrect_post_redirect(webtest):
    """
    Per issue #8104, we should issue an HTTP-308 for a POST
    in /legacy and point the user to the correct endpoint,
    /legacy/

    See: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/308
    """
    resp = webtest.post("/legacy", status=308)
    assert resp.status == (
        "308 An upload was attempted to /legacy, but the expected upload URL is "
        "/legacy/, with the trailing /"
    )

    assert "location" in resp.headers
    assert resp.headers["location"].endswith("/legacy/")
