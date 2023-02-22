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

from tests.common.db.oidc import GitHubPublisherFactory, PendingGitHubPublisherFactory
from warehouse.oidc import models


def test_check_claim_binary():
    wrapped = models._check_claim_binary(str.__eq__)

    assert wrapped("foo", "bar", pretend.stub()) is False
    assert wrapped("foo", "foo", pretend.stub()) is True


class TestOIDCPublisher:
    def test_oidc_publisher_not_default_verifiable(self):
        publisher = models.OIDCPublisher(projects=[])

        assert not publisher.verify_claims(signed_claims={})


class TestGitHubPublisher:
    def test_github_publisher_all_known_claims(self):
        assert models.GitHubPublisher.all_known_claims() == {
            # verifiable claims
            "repository",
            "repository_owner",
            "repository_owner_id",
            "job_workflow_ref",
            # preverified claims
            "iss",
            "iat",
            "nbf",
            "exp",
            "aud",
            # unchecked claims
            "actor",
            "actor_id",
            "jti",
            "sub",
            "ref",
            "sha",
            "run_id",
            "run_number",
            "run_attempt",
            "head_ref",
            "base_ref",
            "event_name",
            "ref_type",
            "repository_id",
            "workflow",
        }

    def test_github_publisher_computed_properties(self):
        publisher = models.GitHubPublisher(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
        )

        for claim_name in publisher.__verifiable_claims__.keys():
            assert getattr(publisher, claim_name) is not None

        assert str(publisher) == "fakeworkflow.yml @ fakeowner/fakerepo"
        assert (
            publisher.publisher_url
            == "https://github.com/fakeowner/fakerepo/blob/HEAD/"
            f".github/workflows/{publisher.workflow_filename}"
        )

    def test_github_publisher_unaccounted_claims(self, monkeypatch):
        publisher = models.GitHubPublisher(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
        )

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(models, "sentry_sdk", sentry_sdk)

        # We don't care if these actually verify, only that they're present.
        signed_claims = {
            claim_name: "fake"
            for claim_name in models.GitHubPublisher.all_known_claims()
        }
        signed_claims["fake-claim"] = "fake"
        assert not publisher.verify_claims(signed_claims=signed_claims)
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "JWT for GitHubPublisher has unaccounted claims: {'fake-claim'}"
            )
        ]

    def test_github_publisher_missing_claims(self, monkeypatch):
        publisher = models.GitHubPublisher(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
        )

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(models, "sentry_sdk", sentry_sdk)

        signed_claims = {
            claim_name: "fake"
            for claim_name in models.GitHubPublisher.all_known_claims()
        }
        # Pop the first signed claim, so that it's the first one to fail.
        signed_claims.pop("sub")
        assert "sub" not in signed_claims
        assert publisher.__verifiable_claims__
        assert not publisher.verify_claims(signed_claims=signed_claims)
        assert sentry_sdk.capture_message.calls == [
            pretend.call("JWT for GitHubPublisher is missing claim: sub")
        ]

    def test_github_publisher_verifies(self, monkeypatch):
        publisher = models.GitHubPublisher(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
        )

        noop_check = pretend.call_recorder(lambda gt, sc, ac: True)
        verifiable_claims = {
            claim_name: noop_check for claim_name in publisher.__verifiable_claims__
        }
        monkeypatch.setattr(publisher, "__verifiable_claims__", verifiable_claims)

        signed_claims = {
            claim_name: "fake"
            for claim_name in models.GitHubPublisher.all_known_claims()
        }
        assert publisher.verify_claims(signed_claims=signed_claims)
        assert len(noop_check.calls) == len(verifiable_claims)

    @pytest.mark.parametrize(
        ("claim", "ref", "valid"),
        [
            # okay: workflow name, followed by a nonempty ref
            (
                "foo/bar/.github/workflows/baz.yml@refs/tags/v0.0.1",
                "refs/tags/v0.0.1",
                True,
            ),
            ("foo/bar/.github/workflows/baz.yml@refs/pulls/6", "refs/pulls/6", True),
            (
                "foo/bar/.github/workflows/baz.yml@refs/heads/main",
                "refs/heads/main",
                True,
            ),
            (
                "foo/bar/.github/workflows/baz.yml@notrailingslash",
                "notrailingslash",
                True,
            ),
            # bad: workflow name, empty or missing ref
            ("foo/bar/.github/workflows/baz.yml@emptyref", "", False),
            ("foo/bar/.github/workflows/baz.yml@missingref", None, False),
            # bad: workflow name with various attempted impersonations
            (
                "foo/bar/.github/workflows/baz.yml@fake.yml@notrailingslash",
                "notrailingslash",
                False,
            ),
            (
                "foo/bar/.github/workflows/baz.yml@fake.yml@refs/pulls/6",
                "refs/pulls/6",
                False,
            ),
            # bad: missing tail or workflow name or otherwise partial
            ("foo/bar/.github/workflows/baz.yml@", "notrailingslash", False),
            ("foo/bar/.github/workflows/@", "notrailingslash", False),
            ("foo/bar/.github/workflows/", "notrailingslash", False),
            ("baz.yml", "notrailingslash", False),
            (
                "foo/bar/.github/workflows/baz.yml@malicious.yml@",
                "notrailingslash",
                False,
            ),
            ("foo/bar/.github/workflows/baz.yml@@", "notrailingslash", False),
            ("", "notrailingslash", False),
        ],
    )
    def test_github_publisher_job_workflow_ref(self, claim, ref, valid):
        publisher = models.GitHubPublisher(
            repository_name="bar",
            repository_owner="foo",
            repository_owner_id=pretend.stub(),
            workflow_filename="baz.yml",
        )

        check = models.GitHubPublisher.__verifiable_claims__["job_workflow_ref"]
        assert check(publisher.job_workflow_ref, claim, {"ref": ref}) is valid


class TestPendingGitHubPublisher:
    def test_reify_does_not_exist_yet(self, db_request):
        pending_publisher = PendingGitHubPublisherFactory.create()
        assert (
            db_request.db.query(models.GitHubPublisher)
            .filter_by(
                repository_name=pending_publisher.repository_name,
                repository_owner=pending_publisher.repository_owner,
                repository_owner_id=pending_publisher.repository_owner_id,
                workflow_filename=pending_publisher.workflow_filename,
            )
            .one_or_none()
            is None
        )
        publisher = pending_publisher.reify(db_request.db)

        # If an OIDC publisher for this pending publisher does not already exist,
        # a new one is created and the pending publisher is marked for deletion.
        assert isinstance(publisher, models.GitHubPublisher)
        assert pending_publisher in db_request.db.deleted
        assert publisher.repository_name == pending_publisher.repository_name
        assert publisher.repository_owner == pending_publisher.repository_owner
        assert publisher.repository_owner_id == pending_publisher.repository_owner_id
        assert publisher.workflow_filename == pending_publisher.workflow_filename

    def test_reify_already_exists(self, db_request):
        existing_publisher = GitHubPublisherFactory.create()
        pending_publisher = PendingGitHubPublisherFactory.create(
            repository_name=existing_publisher.repository_name,
            repository_owner=existing_publisher.repository_owner,
            repository_owner_id=existing_publisher.repository_owner_id,
            workflow_filename=existing_publisher.workflow_filename,
        )
        publisher = pending_publisher.reify(db_request.db)

        # If an OIDC publisher for this pending publisher already exists,
        # it is returned and the pending publisher is marked for deletion.
        assert existing_publisher == publisher
        assert pending_publisher in db_request.db.deleted
