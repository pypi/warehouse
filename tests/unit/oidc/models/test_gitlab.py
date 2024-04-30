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
import sqlalchemy

from tests.common.db.oidc import GitLabPublisherFactory, PendingGitLabPublisherFactory
from warehouse.oidc import errors
from warehouse.oidc.models import _core, gitlab


@pytest.mark.parametrize("claim", ["", "repo", "repo:"])
def test_check_sub(claim):
    assert gitlab._check_sub(pretend.stub(), claim, pretend.stub()) is False


def test_lookup_strategies():
    assert (
        len(gitlab.GitLabPublisher.__lookup_strategies__)
        == len(gitlab.PendingGitLabPublisher.__lookup_strategies__)
        == 2
    )


class TestGitLabPublisher:
    def test_lookup_strategies(self):
        assert (
            len(gitlab.GitLabPublisher.__lookup_strategies__)
            == len(gitlab.PendingGitLabPublisher.__lookup_strategies__)
            == 2
        )

    def test_gitlab_publisher_all_known_claims(self):
        assert gitlab.GitLabPublisher.all_known_claims() == {
            # required verifiable claims
            "sub",
            "project_path",
            "ci_config_ref_uri",
            # required unverifiable claims
            "ref_path",
            "sha",
            # optional verifiable claims
            "environment",
            # preverified claims
            "iss",
            "iat",
            "nbf",
            "exp",
            "aud",
            # unchecked claims
            "project_id",
            "namespace_id",
            "namespace_path",
            "user_id",
            "user_login",
            "user_email",
            "user_identities",
            "pipeline_id",
            "pipeline_source",
            "job_id",
            "ref",
            "ref_type",
            "ref_protected",
            "environment_protected",
            "deployment_tier",
            "environment_action",
            "runner_id",
            "runner_environment",
            "ci_config_sha",
            "project_visibility",
            "jti",
            "user_access_level",
            "groups_direct",
        }

    def test_gitlab_publisher_computed_properties(self):
        publisher = gitlab.GitLabPublisher(
            project="fakerepo",
            namespace="fakeowner",
            workflow_filepath="subfolder/fakeworkflow.yml",
            environment="fakeenv",
        )

        for claim_name in publisher.__required_verifiable_claims__.keys():
            assert getattr(publisher, claim_name) is not None

        assert str(publisher) == "subfolder/fakeworkflow.yml"
        assert publisher.publisher_base_url == "https://gitlab.com/fakeowner/fakerepo"
        assert publisher.publisher_url() == "https://gitlab.com/fakeowner/fakerepo"
        assert (
            publisher.publisher_url({"sha": "somesha"})
            == "https://gitlab.com/fakeowner/fakerepo/commit/somesha"
        )
        assert publisher.stored_claims({"sha": "somesha", "ref_path": "someref"}) == {
            "sha": "somesha",
            "ref_path": "someref",
        }

    def test_gitlab_publisher_unaccounted_claims(self, monkeypatch):
        publisher = gitlab.GitLabPublisher(
            project="fakerepo",
            namespace="fakeowner",
            workflow_filepath="subfolder/fakeworkflow.yml",
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
            for claim_name in gitlab.GitLabPublisher.all_known_claims()
        }
        signed_claims["fake-claim"] = "fake"
        signed_claims["another-fake-claim"] = "also-fake"
        with pytest.raises(errors.InvalidPublisherError) as e:
            publisher.verify_claims(signed_claims=signed_claims)
        assert str(e.value) == "Check failed for required claim 'sub'"
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "JWT for GitLabPublisher has unaccounted claims: "
                "['another-fake-claim', 'fake-claim']"
            )
        ]
        assert scope.fingerprint == ["another-fake-claim", "fake-claim"]

    @pytest.mark.parametrize("missing", ["sub", "ref_path"])
    def test_gitlab_publisher_missing_claims(self, monkeypatch, missing):
        publisher = gitlab.GitLabPublisher(
            project="fakerepo",
            namespace="fakeowner",
            workflow_filepath="subfolder/fakeworkflow.yml",
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
            for claim_name in gitlab.GitLabPublisher.all_known_claims()
        }
        # Pop the missing claim, so that it's missing.
        signed_claims.pop(missing)
        assert missing not in signed_claims
        assert publisher.__required_verifiable_claims__
        with pytest.raises(errors.InvalidPublisherError) as e:
            publisher.verify_claims(signed_claims=signed_claims)
        assert str(e.value) == f"Missing claim {missing!r}"
        assert sentry_sdk.capture_message.calls == [
            pretend.call(f"JWT for GitLabPublisher is missing claim: {missing}")
        ]
        assert scope.fingerprint == [missing]

    def test_gitlab_publisher_missing_optional_claims(self, monkeypatch):
        publisher = gitlab.GitLabPublisher(
            project="fakerepo",
            namespace="fakeowner",
            workflow_filepath="subfolder/fakeworkflow.yml",
            environment="some-environment",  # The optional claim that should be present
        )

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(_core, "sentry_sdk", sentry_sdk)

        signed_claims = {
            claim_name: getattr(publisher, claim_name)
            for claim_name in gitlab.GitLabPublisher.__required_verifiable_claims__
        }
        signed_claims["ref_path"] = "ref"
        signed_claims["sha"] = "sha"
        signed_claims["ci_config_ref_uri"] = publisher.ci_config_ref_uri + "@ref"
        assert publisher.__required_verifiable_claims__
        with pytest.raises(errors.InvalidPublisherError) as e:
            publisher.verify_claims(signed_claims=signed_claims)
        assert str(e.value) == "Check failed for optional claim 'environment'"
        assert sentry_sdk.capture_message.calls == []

    @pytest.mark.parametrize("environment", [None, "some-environment"])
    @pytest.mark.parametrize(
        "missing_claims",
        [set(), gitlab.GitLabPublisher.__optional_verifiable_claims__.keys()],
    )
    def test_gitlab_publisher_verifies(self, monkeypatch, environment, missing_claims):
        publisher = gitlab.GitLabPublisher(
            project="fakerepo",
            namespace="fakeowner",
            workflow_filepath="subfolder/fakeworkflow.yml",
            environment="environment",
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
            for claim_name in gitlab.GitLabPublisher.all_known_claims()
            if claim_name not in missing_claims
        }
        assert publisher.verify_claims(signed_claims=signed_claims)
        assert len(noop_check.calls) == len(verifiable_claims) + len(
            optional_verifiable_claims
        )

    @pytest.mark.parametrize(
        ("truth", "claim", "valid"),
        [
            # invalid: claim should never be empty or missing
            ("", None, False),
            ("foo/bar", None, False),
            ("", "", False),
            ("foo/bar", "", False),
            # valid: exact and case-insensitive matches
            ("foo/bar", "foo/bar", True),
            ("Foo/bar", "foo/bar", True),
            ("Foo/bar", "Foo/bar", True),
            ("foo/bar", "Foo/bar", True),
            ("FOO/bar", "foo/bar", True),
            ("foo/bar", "FOO/bar", True),
            ("foo/Bar", "foo/bar", True),
            ("foo/Bar", "Foo/Bar", True),
            ("foo/bar", "foo/Bar", True),
            ("foo/BAR", "foo/bar", True),
            ("foo/bar", "foo/BAR", True),
        ],
    )
    def test_check_project_path(self, truth, claim, valid):
        check = gitlab.GitLabPublisher.__required_verifiable_claims__["project_path"]
        assert check(truth, claim, pretend.stub()) == valid

    @pytest.mark.parametrize(
        ("claim", "ref_path", "sha", "valid", "expected"),
        [
            # okay: workflow name, followed by a nonempty ref_path
            (
                "gitlab.com/foo/bar//workflows/baz.yml@refs/tags/v0.0.1",
                "refs/tags/v0.0.1",
                "somesha",
                True,
                None,
            ),
            (
                "gitlab.com/foo/bar//workflows/baz.yml@refs/pulls/6",
                "refs/pulls/6",
                "somesha",
                True,
                None,
            ),
            (
                "gitlab.com/foo/bar//workflows/baz.yml@refs/heads/main",
                "refs/heads/main",
                "somesha",
                True,
                None,
            ),
            (
                "gitlab.com/foo/bar//workflows/baz.yml@notrailingslash",
                "notrailingslash",
                "somesha",
                True,
                None,
            ),
            # okay: workflow name, followed by a nonempty sha
            (
                "gitlab.com/foo/bar//workflows/baz.yml@somesha",
                "someref",
                "somesha",
                True,
                None,
            ),
            # bad: either ref_path or sha empty
            (
                "gitlab.com/foo/bar//workflows/baz.yml@somesha",
                None,
                "somesha",
                False,
                "The ref_path and sha claims are empty",
            ),
            (
                "gitlab.com/foo/bar//workflows/baz.yml@somesha",
                "",
                "somesha",
                False,
                "The ref_path and sha claims are empty",
            ),
            (
                "gitlab.com/foo/bar//workflows/baz.yml@missing",
                "someref",
                None,
                False,
                "The ref_path and sha claims are empty",
            ),
            (
                "gitlab.com/foo/bar//workflows/baz.yml@missing",
                "someref",
                "",
                False,
                "The ref_path and sha claims are empty",
            ),
            # bad: both ref_path and sha are missing
            (
                "gitlab.com/foo/bar//workflows/baz.yml@missing",
                None,
                None,
                False,
                "The ref_path and sha claims are empty",
            ),
            (
                "gitlab.com/foo/bar//workflows/baz.yml@missing",
                "",
                "",
                False,
                "The ref_path and sha claims are empty",
            ),
            # bad: workflow name with various attempted impersonations on the ref_path
            (
                "gitlab.com/foo/bar//workflows/baz.yml@fake.yml@notrailingslash",
                "somesha",
                "notrailingslash",
                False,
                "The ci_config_ref_uri claim does not match, expecting one of "
                "['gitlab.com/foo/bar//workflows/baz.yml@notrailingslash', "
                "'gitlab.com/foo/bar//workflows/baz.yml@somesha'], "
                "got 'gitlab.com/foo/bar//workflows/baz.yml@fake.yml@notrailingslash'",
            ),
            (
                "gitlab.com/foo/bar//workflows/baz.yml@fake.yml@refs/pulls/6",
                "somesha",
                "refs/pulls/6",
                False,
                "The ci_config_ref_uri claim does not match, expecting one of "
                "['gitlab.com/foo/bar//workflows/baz.yml@refs/pulls/6', "
                "'gitlab.com/foo/bar//workflows/baz.yml@somesha'], "
                "got 'gitlab.com/foo/bar//workflows/baz.yml@fake.yml@refs/pulls/6'",
            ),
            # bad: missing tail or workflow name or otherwise partial
            (
                "gitlab.com/foo/bar//workflows/baz.yml@",
                "somesha",
                "notrailingslash",
                False,
                "The ci_config_ref_uri claim does not match, expecting one of "
                "['gitlab.com/foo/bar//workflows/baz.yml@notrailingslash', "
                "'gitlab.com/foo/bar//workflows/baz.yml@somesha'], "
                "got 'gitlab.com/foo/bar//workflows/baz.yml@'",
            ),
            (
                "gitlab.com/foo/bar//workflows/@",
                "somesha",
                "notrailingslash",
                False,
                "The ci_config_ref_uri claim does not match, expecting one of "
                "['gitlab.com/foo/bar//workflows/baz.yml@notrailingslash', "
                "'gitlab.com/foo/bar//workflows/baz.yml@somesha'], "
                "got 'gitlab.com/foo/bar//workflows/@'",
            ),
            (
                "gitlab.com/foo/bar//workflows/",
                "somesha",
                "notrailingslash",
                False,
                "The ci_config_ref_uri claim does not match, expecting one of "
                "['gitlab.com/foo/bar//workflows/baz.yml@notrailingslash', "
                "'gitlab.com/foo/bar//workflows/baz.yml@somesha'], "
                "got 'gitlab.com/foo/bar//workflows/'",
            ),
            (
                "baz.yml",
                "somesha",
                "notrailingslash",
                False,
                "The ci_config_ref_uri claim does not match, expecting one of "
                "['gitlab.com/foo/bar//workflows/baz.yml@notrailingslash', "
                "'gitlab.com/foo/bar//workflows/baz.yml@somesha'], "
                "got 'baz.yml'",
            ),
            (
                "gitlab.com/foo/bar//workflows/baz.yml@malicious.yml@",
                "somesha",
                "notrailingslash",
                False,
                "The ci_config_ref_uri claim does not match, expecting one of "
                "['gitlab.com/foo/bar//workflows/baz.yml@notrailingslash', "
                "'gitlab.com/foo/bar//workflows/baz.yml@somesha'], "
                "got 'gitlab.com/foo/bar//workflows/baz.yml@malicious.yml@'",
            ),
            (
                "gitlab.com/foo/bar//workflows/baz.yml@@",
                "somesha",
                "notrailingslash",
                False,
                "The ci_config_ref_uri claim does not match, expecting one of "
                "['gitlab.com/foo/bar//workflows/baz.yml@notrailingslash', "
                "'gitlab.com/foo/bar//workflows/baz.yml@somesha'], "
                "got 'gitlab.com/foo/bar//workflows/baz.yml@@'",
            ),
            ("", None, None, False, "The ci_config_ref_uri claim is empty"),
        ],
    )
    def test_gitlab_publisher_ci_config_ref_uri(
        self, claim, ref_path, sha, valid, expected
    ):
        publisher = gitlab.GitLabPublisher(
            project="bar",
            namespace="foo",
            workflow_filepath="workflows/baz.yml",
        )

        check = gitlab.GitLabPublisher.__required_verifiable_claims__[
            "ci_config_ref_uri"
        ]
        claims = {"ref_path": ref_path, "sha": sha}
        if valid:
            assert check(publisher.ci_config_ref_uri, claim, claims) is True
        else:
            with pytest.raises(errors.InvalidPublisherError) as e:
                check(publisher.ci_config_ref_uri, claim, claims) is True
            assert str(e.value) == expected

    @pytest.mark.parametrize(
        ("truth", "claim", "valid"),
        [
            ("repo:foo/bar", "repo:foo/bar:someotherstuff", True),
            ("repo:foo/bar", "repo:foo/bar:", True),
            ("repo:fOo/BaR", "repo:foo/bar", True),
            ("repo:foo/bar", "repo:fOo/BaR:", True),
            ("repo:foo/bar:someotherstuff", "repo:foo/bar", False),
            ("repo:foo/bar-baz", "repo:foo/bar", False),
            ("repo:foo/bar", "repo:foo/bar-baz", False),
        ],
    )
    def test_gitlab_publisher_sub_claim(self, truth, claim, valid):
        check = gitlab.GitLabPublisher.__required_verifiable_claims__["sub"]
        assert check(truth, claim, pretend.stub()) is valid

    @pytest.mark.parametrize(
        ("truth", "claim", "valid"),
        [
            ("", None, True),
            ("", "", True),
            ("", "some-environment", True),
            ("some-environment", "some-environment", True),
            ("some-environment", "sOmE-eNvIrOnMeNt", False),
            ("some-environment", None, False),
            ("some-environment", "some-other-environment", False),
        ],
    )
    def test_gitlab_publisher_environment_claim(self, truth, claim, valid):
        check = gitlab.GitLabPublisher.__optional_verifiable_claims__["environment"]
        assert check(truth, claim, pretend.stub()) is valid

    def test_gitlab_publisher_duplicates_cant_be_created(self, db_request):
        publisher1 = gitlab.GitLabPublisher(
            project="repository_name",
            namespace="repository_owner",
            workflow_filepath="subfolder/worflow_filename.yml",
            environment="",
        )

        db_request.db.add(publisher1)
        db_request.db.commit()

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            publisher2 = gitlab.GitLabPublisher(
                project="repository_name",
                namespace="repository_owner",
                workflow_filepath="subfolder/worflow_filename.yml",
                environment="",
            )
            db_request.db.add(publisher2)
            db_request.db.commit()


class TestPendingGitLabPublisher:
    def test_reify_does_not_exist_yet(self, db_request):
        pending_publisher = PendingGitLabPublisherFactory.create()
        assert (
            db_request.db.query(gitlab.GitLabPublisher)
            .filter_by(
                project=pending_publisher.project,
                namespace=pending_publisher.namespace,
                workflow_filepath=pending_publisher.workflow_filepath,
                environment=pending_publisher.environment,
            )
            .one_or_none()
            is None
        )
        publisher = pending_publisher.reify(db_request.db)

        # If an OIDC publisher for this pending publisher does not already exist,
        # a new one is created and the pending publisher is marked for deletion.
        assert isinstance(publisher, gitlab.GitLabPublisher)
        assert pending_publisher in db_request.db.deleted
        assert publisher.project == pending_publisher.project
        assert publisher.namespace == pending_publisher.namespace
        assert publisher.workflow_filepath == pending_publisher.workflow_filepath
        assert publisher.environment == pending_publisher.environment

    def test_reify_already_exists(self, db_request):
        existing_publisher = GitLabPublisherFactory.create()
        pending_publisher = PendingGitLabPublisherFactory.create(
            project=existing_publisher.project,
            namespace=existing_publisher.namespace,
            workflow_filepath=existing_publisher.workflow_filepath,
            environment=existing_publisher.environment,
        )
        publisher = pending_publisher.reify(db_request.db)

        # If an OIDC publisher for this pending publisher already exists,
        # it is returned and the pending publisher is marked for deletion.
        assert existing_publisher == publisher
        assert pending_publisher in db_request.db.deleted
