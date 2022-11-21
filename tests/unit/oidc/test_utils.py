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

from sqlalchemy.sql.expression import func, literal

from warehouse.oidc import utils
from warehouse.oidc.models import GitHubProvider


def test_find_provider_by_issuer_bad_issuer_url():
    assert (
        utils.find_provider_by_issuer(
            pretend.stub(), "https://fake-issuer.url", pretend.stub()
        )
        is None
    )


def test_find_provider_by_issuer_github():
    provider = pretend.stub()
    one_or_none = pretend.call_recorder(lambda: provider)
    filter_ = pretend.call_recorder(lambda *a: pretend.stub(one_or_none=one_or_none))
    filter_by = pretend.call_recorder(lambda **kw: pretend.stub(filter=filter_))
    session = pretend.stub(
        query=pretend.call_recorder(lambda cls: pretend.stub(filter_by=filter_by))
    )
    signed_claims = {
        "repository": "foo/bar",
        "job_workflow_ref": "foo/bar/.github/workflows/ci.yml@refs/heads/main",
        "repository_owner_id": "1234",
    }

    assert (
        utils.find_provider_by_issuer(
            session, "https://token.actions.githubusercontent.com", signed_claims
        )
        == provider
    )

    assert session.query.calls == [pretend.call(GitHubProvider)]
    assert filter_by.calls == [
        pretend.call(
            repository_name="bar", repository_owner="foo", repository_owner_id="1234"
        )
    ]

    # SQLAlchemy BinaryExpression objects don't support comparison with __eq__,
    # so we need to dig into the callset and compare the argument manually.
    assert len(filter_.calls) == 1
    assert len(filter_.calls[0].args) == 1
    assert (
        filter_.calls[0]
        .args[0]
        .compare(
            literal("ci.yml@refs/heads/main").like(
                func.concat(GitHubProvider.workflow_filename, "%")
            )
        )
    )

    assert one_or_none.calls == [pretend.call()]
