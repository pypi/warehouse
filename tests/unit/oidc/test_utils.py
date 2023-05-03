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


from warehouse.oidc import utils
from tests.common.db.oidc import GitHubPublisherFactory


def test_find_publisher_by_issuer_bad_issuer_url():
    assert (
        utils.find_publisher_by_issuer(
            pretend.stub(), "https://fake-issuer.url", pretend.stub()
        )
        is None
    )


def test_find_publisher_by_issuer_github(db_request):
    publisher = GitHubPublisherFactory(
        repository_owner="foo",
        repository_name="bar",
        repository_owner_id="1234",
        workflow_filename="ci.yml",
    )

    signed_claims = {
        "repository": "foo/bar",
        "job_workflow_ref": "foo/bar/.github/workflows/ci.yml@refs/heads/main",
        "repository_owner_id": "1234",
    }

    assert (
        utils.find_publisher_by_issuer(
            db_request.db,
            "https://token.actions.githubusercontent.com",
            signed_claims,
        ).id
        == publisher.id
    )


