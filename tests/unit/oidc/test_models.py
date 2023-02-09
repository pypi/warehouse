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

from tests.common.db.oidc import GitHubProviderFactory, PendingGitHubProviderFactory
from warehouse.oidc import models


def test_check_claim_binary():
    wrapped = models._check_claim_binary(str.__eq__)

    assert wrapped("foo", "bar", pretend.stub()) is False
    assert wrapped("foo", "foo", pretend.stub()) is True


class TestOIDCProvider:
    def test_oidc_provider_not_default_verifiable(self):
        provider = models.OIDCProvider(projects=[])

        assert not provider.verify_claims(signed_claims={})


class TestGitHubProvider:
    def test_github_provider_all_known_claims(self):
        assert models.GitHubProvider.all_known_claims() == {
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

    def test_github_provider_computed_properties(self):
        provider = models.GitHubProvider(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
        )

        for claim_name in provider.__verifiable_claims__.keys():
            assert getattr(provider, claim_name) is not None

        assert str(provider) == "fakeworkflow.yml @ fakeowner/fakerepo"
        assert (
            provider.provider_url == "https://github.com/fakeowner/fakerepo/blob/HEAD/"
            f".github/workflows/{provider.workflow_filename}"
        )

    def test_github_provider_unaccounted_claims(self, monkeypatch):
        provider = models.GitHubProvider(
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
            for claim_name in models.GitHubProvider.all_known_claims()
        }
        signed_claims["fake-claim"] = "fake"
        assert not provider.verify_claims(signed_claims=signed_claims)
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "JWT for GitHubProvider has unaccounted claims: {'fake-claim'}"
            )
        ]

    def test_github_provider_missing_claims(self, monkeypatch):
        provider = models.GitHubProvider(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
        )

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(models, "sentry_sdk", sentry_sdk)

        signed_claims = {
            claim_name: "fake"
            for claim_name in models.GitHubProvider.all_known_claims()
        }
        # Pop the first signed claim, so that it's the first one to fail.
        signed_claims.pop("sub")
        assert "sub" not in signed_claims
        assert provider.__verifiable_claims__
        assert not provider.verify_claims(signed_claims=signed_claims)
        assert sentry_sdk.capture_message.calls == [
            pretend.call("JWT for GitHubProvider is missing claim: sub")
        ]

    def test_github_provider_verifies(self, monkeypatch):
        provider = models.GitHubProvider(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
        )

        noop_check = pretend.call_recorder(lambda gt, sc, ac: True)
        verifiable_claims = {
            claim_name: noop_check for claim_name in provider.__verifiable_claims__
        }
        monkeypatch.setattr(provider, "__verifiable_claims__", verifiable_claims)

        signed_claims = {
            claim_name: "fake"
            for claim_name in models.GitHubProvider.all_known_claims()
        }
        assert provider.verify_claims(signed_claims=signed_claims)
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
    def test_github_provider_job_workflow_ref(self, claim, ref, valid):
        provider = models.GitHubProvider(
            repository_name="bar",
            repository_owner="foo",
            repository_owner_id=pretend.stub(),
            workflow_filename="baz.yml",
        )

        check = models.GitHubProvider.__verifiable_claims__["job_workflow_ref"]
        assert check(provider.job_workflow_ref, claim, {"ref": ref}) is valid


class TestPendingGitHubProvider:
    def test_reify_does_not_exist_yet(self, db_request):
        pending_provider = PendingGitHubProviderFactory.create()
        assert (
            db_request.db.query(models.GitHubProvider)
            .filter_by(
                repository_name=pending_provider.repository_name,
                repository_owner=pending_provider.repository_owner,
                repository_owner_id=pending_provider.repository_owner_id,
                workflow_filename=pending_provider.workflow_filename,
            )
            .one_or_none()
            is None
        )
        provider = pending_provider.reify(db_request.db)

        # If an OIDC provider for this pending provider does not already exist,
        # a new one is created and the pending provider is marked for deletion.
        assert isinstance(provider, models.GitHubProvider)
        assert pending_provider in db_request.db.deleted
        assert provider.repository_name == pending_provider.repository_name
        assert provider.repository_owner == pending_provider.repository_owner
        assert provider.repository_owner_id == pending_provider.repository_owner_id
        assert provider.workflow_filename == pending_provider.workflow_filename

    def test_reify_already_exists(self, db_request):
        existing_provider = GitHubProviderFactory.create()
        pending_provider = PendingGitHubProviderFactory.create(
            repository_name=existing_provider.repository_name,
            repository_owner=existing_provider.repository_owner,
            repository_owner_id=existing_provider.repository_owner_id,
            workflow_filename=existing_provider.workflow_filename,
        )
        provider = pending_provider.reify(db_request.db)

        # If an OIDC provider for this pending provider already exists,
        # it is returned and the pending provider is marked for deletion.
        assert existing_provider == provider
        assert pending_provider in db_request.db.deleted
