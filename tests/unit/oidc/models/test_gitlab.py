# SPDX-License-Identifier: Apache-2.0

import pretend
import psycopg
import pytest

from tests.common.db.oidc import GitLabPublisherFactory, PendingGitLabPublisherFactory
from tests.common.db.organizations import OrganizationOIDCIssuerFactory
from warehouse.oidc import errors
from warehouse.oidc.models import _core, gitlab

PROJECT_NAME = "project_name"
NAMESPACE = "project_owner"


@pytest.mark.parametrize(
    ("ci_config_ref_uri", "expected"),
    [
        # Well-formed `ci_config_ref_uri`s, including obnoxious ones.
        ("gitlab.com/foo/bar//notnested.yml@/some/ref", "notnested.yml"),
        ("gitlab.com/foo/bar//notnested.yaml@/some/ref", "notnested.yaml"),
        ("gitlab.com/foo/bar//basic/basic.yml@/some/ref", "basic/basic.yml"),
        (
            "gitlab.com/foo/bar//more/nested/example.yml@/some/ref",
            "more/nested/example.yml",
        ),
        (
            "gitlab.com/foo/bar//too//many//slashes.yml@/some/ref",
            "too//many//slashes.yml",
        ),
        ("gitlab.com/foo/bar//has-@.yml@/some/ref", "has-@.yml"),
        ("gitlab.com/foo/bar//foo.bar.yml@/some/ref", "foo.bar.yml"),
        ("gitlab.com/foo/bar//foo.yml.bar.yml@/some/ref", "foo.yml.bar.yml"),
        ("gitlab.com/foo/bar//foo.yml@bar.yml@/some/ref", "foo.yml@bar.yml"),
        ("gitlab.com/foo/bar//@foo.yml@bar.yml@/some/ref", "@foo.yml@bar.yml"),
        (
            "gitlab.com/foo/bar//@.yml.foo.yml@bar.yml@/some/ref",
            "@.yml.foo.yml@bar.yml",
        ),
        ("gitlab.com/foo/bar//a.yml@/some/ref", "a.yml"),
        ("gitlab.com/foo/bar//a/b.yml@/some/ref", "a/b.yml"),
        # Custom domain.
        ("gitlab.example.com/foo/bar//example.yml@/some/ref", "example.yml"),
        # Malformed `ci_config_ref_uri`s.
        ("gitlab.com/foo/bar//notnested.wrongsuffix@/some/ref", None),
        ("gitlab.com/foo/bar//@/some/ref", None),
        ("gitlab.com/foo/bar//.yml@/some/ref", None),
        ("gitlab.com/foo/bar//.yaml@/some/ref", None),
        ("gitlab.com/foo/bar//somedir/.yaml@/some/ref", None),
    ],
)
def test_extract_workflow_filename(ci_config_ref_uri, expected):
    assert gitlab._extract_workflow_filepath(ci_config_ref_uri) == expected


@pytest.mark.parametrize("claim", ["", "repo", "repo:"])
def test_check_sub(claim):
    assert gitlab._check_sub(pretend.stub(), claim, pretend.stub()) is False


class TestGitLabPublisher:
    @pytest.mark.parametrize("environment", [None, "some_environment"])
    def test_lookup_fails_invalid_ci_config_ref_uri(self, environment):
        signed_claims = {
            "iss": "https://gitlab.com",
            "project_path": "foo/bar",
            "ci_config_ref_uri": ("gitlab.com/foo/bar//example/.yml@refs/heads/main"),
        }

        if environment:
            signed_claims["environment"] = environment

        # The `ci_config_ref_uri` is malformed, so no queries are performed.
        with pytest.raises(
            errors.InvalidPublisherError,
            match="Could not extract workflow filename from OIDC claims",
        ):
            gitlab.GitLabPublisher.lookup_by_claims(pretend.stub(), signed_claims)

    @pytest.mark.parametrize(
        ("configured_namespace", "configured_project", "project_path"),
        [
            (
                "Foo",
                "Bar",
                "foo/bar",
            ),
            (
                "foo",
                "bar",
                "Foo/Bar",
            ),
        ],
    )
    def test_lookup_succeeds_with_mixed_case_project_path(
        self, db_request, configured_namespace, configured_project, project_path
    ):
        # Test that we find a matching publisher when the project_path claims match
        # even if the case is different.
        stored_publisher = GitLabPublisherFactory(
            namespace=configured_namespace,
            project=configured_project,
            workflow_filepath=".gitlab-ci.yml",
            environment="",
        )

        signed_claims = {
            "iss": "https://gitlab.com",
            "project_path": project_path,
            "ci_config_ref_uri": "gitlab.com/foo/bar//.gitlab-ci.yml@refs/heads/main",
            "environment": "some_environment",
        }

        publisher = gitlab.GitLabPublisher.lookup_by_claims(
            db_request.db, signed_claims
        )

        assert publisher.id == stored_publisher.id
        assert publisher.environment == stored_publisher.environment

    @pytest.mark.parametrize("environment", ["SomeEnvironment", "SOME_ENVIRONMENT"])
    def test_lookup_succeeds_with_non_lowercase_environment(
        self, db_request, environment
    ):
        # Test that we find a matching publisher when the environment claims match
        # If we incorrectly normalized the incoming capitalized claim, we wouldn't
        # find the matching publisher.
        stored_publisher = GitLabPublisherFactory(
            id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            namespace="foo",
            project="bar",
            workflow_filepath=".gitlab-ci.yml",
            environment=environment,
        )

        signed_claims = {
            "iss": "https://gitlab.com",
            "project_path": "foo/bar",
            "ci_config_ref_uri": ("gitlab.com/foo/bar//.gitlab-ci.yml@refs/heads/main"),
            "environment": environment,
        }

        publisher = gitlab.GitLabPublisher.lookup_by_claims(
            db_request.db, signed_claims
        )

        assert publisher.id == stored_publisher.id
        assert publisher.environment == environment

    @pytest.mark.parametrize("environment", ["SomeEnvironment", "SOME_ENVIRONMENT"])
    def test_lookup_is_case_sensitive_for_environment(self, db_request, environment):
        # Test that we don't find a matching publisher when the environment claims don't
        # exactly match.
        # If we incorrectly normalized the incoming capitalized claim, we would match
        # a publisher that has a different environment.
        GitLabPublisherFactory(
            id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            namespace="foo",
            project="bar",
            workflow_filepath=".gitlab-ci.yml",
            # stored environment is all lowercase, doesn't match incoming claims
            environment=environment.lower(),
        )

        signed_claims = {
            "iss": "https://gitlab.com",
            "project_path": "foo/bar",
            "ci_config_ref_uri": ("gitlab.com/foo/bar//.gitlab-ci.yml@refs/heads/main"),
            "environment": environment,
        }

        with pytest.raises(errors.InvalidPublisherError) as e:
            gitlab.GitLabPublisher.lookup_by_claims(db_request.db, signed_claims)
        assert str(e.value) == "Publisher with matching claims was not found"

    @pytest.mark.parametrize("environment", ["", "some_environment"])
    @pytest.mark.parametrize(
        ("workflow_filepath_a", "workflow_filepath_b"),
        [
            ("workflows/release_pypi/ci.yml", "workflows/release-pypi/ci.yml"),
            ("workflows/release%pypi/ci.yml", "workflows/release-pypi/ci.yml"),
        ],
    )
    def test_lookup_escapes(
        self, db_request, environment, workflow_filepath_a, workflow_filepath_b
    ):
        GitLabPublisherFactory(
            id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            namespace="foo",
            project="bar",
            workflow_filepath=workflow_filepath_a,
            environment=environment,
        )
        GitLabPublisherFactory(
            id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            namespace="foo",
            project="bar",
            workflow_filepath=workflow_filepath_b,
            environment=environment,
        )

        for workflow_filepath in (workflow_filepath_a, workflow_filepath_b):
            signed_claims = {
                "iss": "https://gitlab.com",
                "project_path": "foo/bar",
                "ci_config_ref_uri": (
                    f"gitlab.com/foo/bar//{workflow_filepath}@refs/heads/main"
                ),
            }

            if environment:
                signed_claims["environment"] = environment

            assert (
                gitlab.GitLabPublisher.lookup_by_claims(
                    db_request.db, signed_claims
                ).workflow_filepath
                == workflow_filepath
            )

    def test_lookup_no_matching_publisher(self, db_request):
        signed_claims = {
            "iss": "https://gitlab.com",
            "project_path": "foo/bar",
            "ci_config_ref_uri": ("gitlab.com/foo/bar//.gitlab-ci.yml@refs/heads/main"),
        }
        with pytest.raises(errors.InvalidPublisherError) as e:
            gitlab.GitLabPublisher.lookup_by_claims(db_request.db, signed_claims)
        assert str(e.value) == "Publisher with matching claims was not found"

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
            "jti",
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
            "user_access_level",
            "groups_direct",
            "job_namespace_id",
            "job_namespace_path",
            "job_project_id",
            "job_project_path",
        }

    def test_gitlab_publisher_computed_properties(self):
        publisher = gitlab.GitLabPublisher(
            project="fakerepo",
            namespace="fakeowner",
            workflow_filepath="subfolder/fakeworkflow.yml",
            environment="fakeenv",
            issuer_url="https://gitlab.com",
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

    def test_gitlab_publisher_admin_details_with_environment(self):
        publisher = gitlab.GitLabPublisher(
            project="fakerepo",
            namespace="fakeowner",
            workflow_filepath="subfolder/fakeworkflow.yml",
            environment="fakeenv",
            issuer_url="https://gitlab.com",
        )

        assert publisher.admin_details == [
            ("Project", "fakeowner/fakerepo"),
            ("Workflow", "subfolder/fakeworkflow.yml"),
            ("Issuer URL", "https://gitlab.com"),
            ("Environment", "fakeenv"),
        ]

    def test_gitlab_publisher_admin_details_without_environment(self):
        publisher = gitlab.GitLabPublisher(
            project="fakerepo",
            namespace="fakeowner",
            workflow_filepath="subfolder/fakeworkflow.yml",
            environment="",
            issuer_url="https://gitlab.com",
        )

        assert publisher.admin_details == [
            ("Project", "fakeowner/fakerepo"),
            ("Workflow", "subfolder/fakeworkflow.yml"),
            ("Issuer URL", "https://gitlab.com"),
        ]

    def test_gitlab_publisher_unaccounted_claims(self, monkeypatch):
        scope = pretend.stub()
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda s: None),
            new_scope=pretend.call_recorder(
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

        gitlab.GitLabPublisher.check_claims_existence(signed_claims)
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "JWT for GitLabPublisher has unaccounted claims: "
                "['another-fake-claim', 'fake-claim']"
            )
        ]
        assert scope.fingerprint == ["another-fake-claim", "fake-claim"]

    @pytest.mark.parametrize(
        "missing",
        gitlab.GitLabPublisher.__required_verifiable_claims__.keys()
        | gitlab.GitLabPublisher.__required_unverifiable_claims__,
    )
    def test_gitlab_publisher_missing_claims(self, monkeypatch, missing):
        publisher = gitlab.GitLabPublisher(
            project="fakerepo",
            namespace="fakeowner",
            workflow_filepath="subfolder/fakeworkflow.yml",
            issuer_url="https://gitlab.com",
        )

        scope = pretend.stub()
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda s: None),
            new_scope=pretend.call_recorder(
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
            gitlab.GitLabPublisher.check_claims_existence(signed_claims)
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
            issuer_url="https://gitlab.com",
        )

        sentry_sdk = pretend.stub(capture_message=pretend.call_recorder(lambda s: None))
        monkeypatch.setattr(_core, "sentry_sdk", sentry_sdk)

        service = pretend.stub(
            jwt_identifier_exists=pretend.call_recorder(lambda s: False)
        )

        signed_claims = {
            claim_name: getattr(publisher, claim_name)
            for claim_name in gitlab.GitLabPublisher.__required_verifiable_claims__
        }
        signed_claims["ref_path"] = "ref"
        signed_claims["sha"] = "sha"
        signed_claims["ci_config_ref_uri"] = publisher.ci_config_ref_uri + "@ref"
        assert publisher.__required_verifiable_claims__
        with pytest.raises(errors.InvalidPublisherError) as e:
            publisher.verify_claims(
                signed_claims=signed_claims, publisher_service=service
            )
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
            issuer_url="https://gitlab.com",
        )

        noop_check = pretend.call_recorder(lambda gt, sc, ac, **kwargs: True)
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
        assert publisher.verify_claims(
            signed_claims=signed_claims, publisher_service=pretend.stub()
        )
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
            issuer_url="https://gitlab.com",
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
            issuer_url="https://gitlab.com",
        )

        db_request.db.add(publisher1)
        db_request.db.commit()

        publisher2 = gitlab.GitLabPublisher(
            project="repository_name",
            namespace="repository_owner",
            workflow_filepath="subfolder/worflow_filename.yml",
            environment="",
            issuer_url="https://gitlab.com",
        )
        db_request.db.add(publisher2)

        with pytest.raises(psycopg.errors.UniqueViolation):
            db_request.db.commit()

    @pytest.mark.parametrize(
        ("project_name", "namespace", "url", "expected"),
        [
            (
                PROJECT_NAME,
                NAMESPACE,
                f"https://gitlab.com/{NAMESPACE}/{PROJECT_NAME}.git",
                True,
            ),
            (
                "Project_Name",
                NAMESPACE,
                f"https://gitlab.com/{NAMESPACE}/{PROJECT_NAME}.git",
                True,
            ),
            (
                PROJECT_NAME,
                "Project_Owner",
                f"https://gitlab.com/{NAMESPACE}/{PROJECT_NAME}.git",
                True,
            ),
            (
                PROJECT_NAME,
                NAMESPACE,
                f"https://gitlab.com/{NAMESPACE}/{PROJECT_NAME}.git/",
                True,
            ),
            (
                PROJECT_NAME,
                NAMESPACE,
                f"https://gitlab.com/{NAMESPACE}/{PROJECT_NAME}.git/issues",
                False,
            ),
            (
                PROJECT_NAME,
                NAMESPACE,
                f"https://{NAMESPACE}.gitlab.io/{PROJECT_NAME}/",
                True,
            ),
            (
                PROJECT_NAME,
                NAMESPACE,
                f"https://{NAMESPACE}.gitlab.io/{PROJECT_NAME}/subpage/",
                True,
            ),
            (
                PROJECT_NAME,
                "owner.with.dot",
                f"https://owner.with.dot.gitlab.io/{PROJECT_NAME}",
                True,
            ),
            (
                PROJECT_NAME,
                NAMESPACE,
                f"https://gitlab.com/{NAMESPACE.replace('e', 'E')}/"
                f"{PROJECT_NAME.replace('r', 'R')}/",
                True,
            ),
            (  # Unique domains are not supported
                PROJECT_NAME,
                NAMESPACE,
                f"https://{PROJECT_NAME}-123456.gitlab.io/",
                False,
            ),
            # Project name is not properly formed
            (PROJECT_NAME, NAMESPACE, f"https://{NAMESPACE}.gitlab.io/", False),
            (
                f"{NAMESPACE}.gitlab.io",
                NAMESPACE,
                f"https://{NAMESPACE}.gitlab.io",
                True,
            ),
            (
                f"{NAMESPACE}.gitlab.io",
                NAMESPACE,
                f"https://{NAMESPACE}.gitlab.io/",
                True,
            ),
            (
                f"{NAMESPACE}.gitlab.io",
                NAMESPACE,
                f"https://{NAMESPACE}.gitlab.io/subpage",
                True,
            ),
            (  # Only for user/group own pages
                "project_name.gitlab.io",
                NAMESPACE,
                f"https://{NAMESPACE}.gitlab.io/subpage",
                False,
            ),
            (
                "project",
                "group/subgroup",
                "https://group.gitlab.io/subgroup/project/",
                True,
            ),
            (
                "project",
                "group/subgroup",
                "https://group.gitlab.io/subgroup/project/about",
                True,
            ),
            # The namespace should only contain 1 element
            ("group.gitlab.io", "group/subgroup", "https://group.gitlab.io/", False),
        ],
    )
    def test_gitlab_publisher_verify_url(
        self, project_name: str, namespace: str, url: str, expected: bool
    ):
        publisher = gitlab.GitLabPublisher(
            project=project_name,
            namespace=namespace,
            workflow_filepath="workflow_filename.yml",
            environment="",
            issuer_url="https://gitlab.com",
        )
        assert publisher.verify_url(url) == expected

    @pytest.mark.parametrize("environment", ["", "some-env"])
    def test_gitlab_publisher_attestation_identity(self, environment):
        publisher = gitlab.GitLabPublisher(
            project="project",
            namespace="group/subgroup",
            workflow_filepath="workflow_filename.yml",
            environment=environment,
            issuer_url="https://gitlab.com",
        )

        identity = publisher.attestation_identity
        assert identity is not None
        assert identity.repository == publisher.project_path
        assert identity.workflow_filepath == publisher.workflow_filepath

        if not environment:
            assert identity.environment is None
        else:
            assert identity.environment == publisher.environment

    @pytest.mark.parametrize("exists_in_db", [True, False])
    def test_exists(self, db_request, exists_in_db):
        publisher = gitlab.GitLabPublisher(
            project="repository_name",
            namespace="repository_owner",
            workflow_filepath="subfolder/worflow_filename.yml",
            environment="",
            issuer_url="https://gitlab.com",
        )

        if exists_in_db:
            db_request.db.add(publisher)
            db_request.db.flush()

        assert publisher.exists(db_request.db) == exists_in_db

    def test_get_available_issuer_urls_default(self):
        """By default, there's a single known GitLab issuer URL."""
        issuer_urls = gitlab.GitLabPublisher.get_available_issuer_urls()
        assert issuer_urls == ["https://gitlab.com"]

    def test_get_available_issuer_urls_custom(self, db_session):
        """If a custom GitLab issuer URL is configured for the org, it is included."""
        org_oidc_issuer = OrganizationOIDCIssuerFactory(issuer_type="gitlab")

        issuer_urls = gitlab.GitLabPublisher.get_available_issuer_urls(
            org_oidc_issuer.organization
        )

        assert issuer_urls == ["https://gitlab.com", org_oidc_issuer.issuer_url]

    def test_get_available_issuer_urls_multiple_custom(self, db_session):
        """
        If multiple custom GitLab issuer URLs are configured for the org,
        they are all included, and sorted alphabetically after the default.
        """
        org_oidc_issuer1 = OrganizationOIDCIssuerFactory(
            issuer_type="gitlab", issuer_url="https://zzz.example.com"
        )
        org_oidc_issuer2 = OrganizationOIDCIssuerFactory(
            organization=org_oidc_issuer1.organization,
            issuer_type="gitlab",
            issuer_url="https://aaa.example.com",
        )

        issuer_urls = gitlab.GitLabPublisher.get_available_issuer_urls(
            org_oidc_issuer1.organization
        )

        assert issuer_urls == [
            "https://gitlab.com",
            org_oidc_issuer2.issuer_url,
            org_oidc_issuer1.issuer_url,
        ]

    def test_get_available_issuer_urls_custom_non_gitlab(self, db_session):
        """
        If a custom OIDC issuer URL of a different type is configured for the org,
        it is not included.
        """
        org_oidc_issuer = OrganizationOIDCIssuerFactory(issuer_type="github")

        issuer_urls = gitlab.GitLabPublisher.get_available_issuer_urls(
            org_oidc_issuer.organization
        )

        assert issuer_urls == ["https://gitlab.com"]


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

    def test_reify_with_custom_issuer_url(self, db_request):
        custom_issuer_url = "https://gitlab.custom-domain.com"
        pending_publisher = PendingGitLabPublisherFactory.create(
            issuer_url=custom_issuer_url
        )
        publisher = pending_publisher.reify(db_request.db)

        assert publisher.issuer_url == custom_issuer_url
        assert isinstance(publisher, gitlab.GitLabPublisher)
