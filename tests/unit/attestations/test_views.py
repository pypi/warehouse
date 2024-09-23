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

from warehouse.attestations import views


def test_provenance_for_file_not_enabled():
    request = pretend.stub(
        flags=pretend.stub(enabled=lambda *a: True),
    )

    response = views.provenance_for_file(pretend.stub(), request)
    assert response.status_code == 403
    assert response.json == {"message": "Attestations temporarily disabled"}


def test_provenance_for_file_not_present():
    request = pretend.stub(
        flags=pretend.stub(enabled=lambda *a: False),
    )
    file = pretend.stub(provenance=None, filename="fake-1.2.3.tar.gz")

    response = views.provenance_for_file(file, request)
    assert response.status_code == 404
    assert response.json == {"message": "No provenance available for fake-1.2.3.tar.gz"}
