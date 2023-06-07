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
from warehouse.oidc.models import _core, github


@pytest.mark.parametrize("claim", ["", "repo", "repo:"])
def test_check_sub(claim):
    assert github._check_sub(pretend.stub(), claim, pretend.stub()) is False


def test_lookup_strategies():
    assert (
        len(github.GitHubPublisher.__lookup_strategies__)
        == len(github.PendingGitHubPublisher.__lookup_strategies__)
        == 2
    )


class TestGitHubPublisher:
    def test_lookup_strategies(self):
        assert (
            len(github.GitHubPublisher.__lookup_strategies__)
            == len(github.PendingGitHubPublisher.__lookup_strategies__)
            == 2
        )

    def test_github_publisher_all_known_claims(self):
        assert github.GitHubPublisher.all_known_claims() == {
            # verifiable claims
            "sub",
            "repository",
            "repository_owner",
            "repository_owner_id",
            "job_workflow_ref",
            # optional verifiable claims
            "environment",
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
            "repository_visibility",
            "workflow_sha",
            "job_workflow_sha",
            "workflow_ref",
            "runner_environment",
            "environment_node_id",
            "enterprise",
        }

    def test_github_publisher_computed_properties(self):
        publisher = github.GitHubPublisher(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
            environment="fakeenv",
        )

        for claim_name in publisher.__required_verifiable_claims__.keys():
            assert getattr(publisher, claim_name) is not None

        assert str(publisher) == "fakeworkflow.yml"
        assert publisher.publisher_url() == "https://github.com/fakeowner/fakerepo"
        assert (
            publisher.publisher_url({"sha": "somesha"})
            == "https://github.com/fakeowner/fakerepo/commit/somesha"
        )

    def test_github_publisher_unaccounted_claims(self, monkeypatch):
        publisher = github.GitHubPublisher(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
        )

        scope = pretend.stub()
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda s: None),
            push_scope=pretend.call_recorder(
                lambda: pretend.stub(
                    __enter__=lambda *a: scope, __exit__=lambda *a: None
                )
            ),
        )
        monkeypatch.setattr(_core, "sentry_sdk", sentry_sdk)

        # We don't care if these actually verify, only that they're present.
        signed_claims = {
            claim_name: "fake"
            for claim_name in github.GitHubPublisher.all_known_claims()
        }
        signed_claims["fake-claim"] = "fake"
        signed_claims["another-fake-claim"] = "also-fake"
        assert not publisher.verify_claims(signed_claims=signed_claims)
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "JWT for GitHubPublisher has unaccounted claims: "
                "['another-fake-claim', 'fake-claim']"
            )
        ]
        assert scope.fingerprint == ["another-fake-claim", "fake-claim"]

    def test_github_publisher_missing_claims(self, monkeypatch):
        publisher = github.GitHubPublisher(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
        )

        scope = pretend.stub()
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda s: None),
            push_scope=pretend.call_recorder(
                lambda: pretend.stub(
                    __enter__=lambda *a: scope, __exit__=lambda *a: None
                )
            ),
        )
        monkeypatch.setattr(_core, "sentry_sdk", sentry_sdk)

        signed_claims = {
            claim_name: "fake"
            for claim_name in github.GitHubPublisher.all_known_claims()
        }
        # Pop the first signed claim, so that it's the first one to fail.
        signed_claims.pop("sub")
        assert "sub" not in signed_claims
        assert publisher.__required_verifiable_claims__
        assert not publisher.verify_claims(signed_claims=signed_claims)
        assert sentry_sdk.capture_message.calls == [
            pretend.call("JWT for GitHubPublisher is missing claim: sub")
        ]
        assert scope.fingerprint == ["sub"]

    def test_github_publisher_missing_optional_claims(self, monkeypatch):
        publisher = github.GitHubPublisher(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
            environment="some-environment",  # The optional claim that should be present
        )

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(_core, "sentry_sdk", sentry_sdk)

        signed_claims = {
            claim_name: getattr(publisher, claim_name)
            for claim_name in github.GitHubPublisher.__required_verifiable_claims__
        }
        signed_claims["ref"] = "ref"
        signed_claims["job_workflow_ref"] = publisher.job_workflow_ref + "@ref"
        assert publisher.__required_verifiable_claims__
        assert not publisher.verify_claims(signed_claims=signed_claims)
        assert sentry_sdk.capture_message.calls == []

    @pytest.mark.parametrize("environment", [None, "some-environment"])
    @pytest.mark.parametrize(
        "missing_claims",
        [set(), github.GitHubPublisher.__optional_verifiable_claims__.keys()],
    )
    def test_github_publisher_verifies(self, monkeypatch, environment, missing_claims):
        publisher = github.GitHubPublisher(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
            environment=environment,
        )

        noop_check = pretend.call_recorder(lambda gt, sc, ac: True)
        verifiable_claims = {
            claim_name: noop_check
            for claim_name in publisher.__required_verifiable_claims__
        }
        monkeypatch.setattr(
            publisher, "__required_verifiable_claims__", verifiable_claims
        )
        optional_verifiable_claims = {
            claim_name: noop_check
            for claim_name in publisher.__optional_verifiable_claims__
        }
        monkeypatch.setattr(
            publisher, "__optional_verifiable_claims__", optional_verifiable_claims
        )

        signed_claims = {
            claim_name: "fake"
            for claim_name in github.GitHubPublisher.all_known_claims()
            if claim_name not in missing_claims
        }
        assert publisher.verify_claims(signed_claims=signed_claims)
        assert len(noop_check.calls) == len(verifiable_claims) + len(
            optional_verifiable_claims
        )

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
        publisher = github.GitHubPublisher(
            repository_name="bar",
            repository_owner="foo",
            repository_owner_id=pretend.stub(),
            workflow_filename="baz.yml",
        )

        check = github.GitHubPublisher.__required_verifiable_claims__[
            "job_workflow_ref"
        ]
        assert check(publisher.job_workflow_ref, claim, {"ref": ref}) is valid

    @pytest.mark.parametrize(
        ("truth", "claim", "valid"),
        [
            ("repo:foo/bar", "repo:foo/bar:someotherstuff", True),
            ("repo:foo/bar", "repo:foo/bar:", True),
            ("repo:foo/bar:someotherstuff", "repo:foo/bar", False),
            ("repo:foo/bar-baz", "repo:foo/bar", False),
            ("repo:foo/bar", "repo:foo/bar-baz", False),
        ],
    )
    def test_github_publisher_sub_claim(self, truth, claim, valid):
        check = github.GitHubPublisher.__required_verifiable_claims__["sub"]
        assert check(truth, claim, pretend.stub()) is valid

    @pytest.mark.parametrize(
        ("truth", "claim", "valid"),
        [
            (None, None, True),
            (None, "some-environment", True),
            ("some-environment", "some-environment", True),
            ("some-environment", "sOmE-eNvIrOnMeNt", True),
            ("some-environment", None, False),
            ("some-environment", "some-other-environment", False),
        ],
    )
    def test_github_publisher_environment_claim(self, truth, claim, valid):
        check = github.GitHubPublisher.__optional_verifiable_claims__["environment"]
        assert check(truth, claim, pretend.stub()) is valid


class TestPendingGitHubPublisher:
    def test_reify_does_not_exist_yet(self, db_request):
        pending_publisher = PendingGitHubPublisherFactory.create()
        assert (
            db_request.db.query(github.GitHubPublisher)
            .filter_by(
                repository_name=pending_publisher.repository_name,
                repository_owner=pending_publisher.repository_owner,
                repository_owner_id=pending_publisher.repository_owner_id,
                workflow_filename=pending_publisher.workflow_filename,
                environment=pending_publisher.environment,
            )
            .one_or_none()
            is None
        )
        publisher = pending_publisher.reify(db_request.db)

        # If an OIDC publisher for this pending publisher does not already exist,
        # a new one is created and the pending publisher is marked for deletion.
        assert isinstance(publisher, github.GitHubPublisher)
        assert pending_publisher in db_request.db.deleted
        assert publisher.repository_name == pending_publisher.repository_name
        assert publisher.repository_owner == pending_publisher.repository_owner
        assert publisher.repository_owner_id == pending_publisher.repository_owner_id
        assert publisher.workflow_filename == pending_publisher.workflow_filename
        assert publisher.environment == pending_publisher.environment

    def test_reify_already_exists(self, db_request):
        existing_publisher = GitHubPublisherFactory.create()
        pending_publisher = PendingGitHubPublisherFactory.create(
            repository_name=existing_publisher.repository_name,
            repository_owner=existing_publisher.repository_owner,
            repository_owner_id=existing_publisher.repository_owner_id,
            workflow_filename=existing_publisher.workflow_filename,
            environment=existing_publisher.environment,
        )
        publisher = pending_publisher.reify(db_request.db)

        # If an OIDC publisher for this pending publisher already exists,
        # it is returned and the pending publisher is marked for deletion.
        assert existing_publisher == publisher
        assert pending_publisher in db_request.db.deleted
