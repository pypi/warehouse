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

from tests.common.db.accounts import UserFactory
from tests.common.db.oidc import PendingGitHubProviderFactory
from warehouse.events.tags import EventTag
from warehouse.oidc import utils
from warehouse.oidc.models import GitHubProvider, PendingGitHubProvider
from warehouse.packaging.models import Project


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


def test_reify_pending_provider(db_request):
    user = UserFactory.create()
    pending_provider = PendingGitHubProviderFactory.create(added_by=user)

    project, provider = utils.reify_pending_provider(
        db_request.db, pending_provider, "0.0.0.0"
    )

    assert (project.events[0].tag, project.events[0].additional) == (
        EventTag.Project.ProjectCreate,
        {"created_by": user.username},
    )
    assert (project.events[1].tag, project.events[1].additional) == (
        EventTag.Project.RoleAdd,
        {
            "submitted_by": user.username,
            "role_name": "Owner",
            "target_user": user.username,
        },
    )

    assert isinstance(project, Project)
    assert project.name == pending_provider.project_name
    assert user.projects == [project]

    assert isinstance(provider, GitHubProvider)
    # The pending provider should no longer exist.
    assert (
        db_request.db.query(PendingGitHubProvider)
        .filter_by(
            repository_name=provider.repository_name,
            repository_owner=provider.repository_owner,
            repository_owner_id=provider.repository_owner_id,
            workflow_filename=provider.workflow_filename,
        )
        .one_or_none()
        is None
    )
