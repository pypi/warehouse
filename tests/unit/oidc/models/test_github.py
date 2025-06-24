# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest
import sqlalchemy

from tests.common.db.oidc import GitHubPublisherFactory, PendingGitHubPublisherFactory
from warehouse.oidc import errors
from warehouse.oidc.models import _core, github


@pytest.mark.parametrize(
    ("workflow_ref", "expected"),
    [
        # Well-formed workflow refs, including exceedingly obnoxious ones
        # with `@` or extra suffixes or `git` refs that look like workflows.
        ("foo/bar/.github/workflows/basic.yml@refs/heads/main", "basic.yml"),
        ("foo/bar/.github/workflows/basic.yaml@refs/heads/main", "basic.yaml"),
        ("foo/bar/.github/workflows/has-dash.yml@refs/heads/main", "has-dash.yml"),
        (
            "foo/bar/.github/workflows/has--dashes.yml@refs/heads/main",
            "has--dashes.yml",
        ),
        (
            "foo/bar/.github/workflows/has--dashes-.yml@refs/heads/main",
            "has--dashes-.yml",
        ),
        ("foo/bar/.github/workflows/has.period.yml@refs/heads/main", "has.period.yml"),
        (
            "foo/bar/.github/workflows/has..periods.yml@refs/heads/main",
            "has..periods.yml",
        ),
        (
            "foo/bar/.github/workflows/has..periods..yml@refs/heads/main",
            "has..periods..yml",
        ),
        (
            "foo/bar/.github/workflows/has_underscore.yml@refs/heads/main",
            "has_underscore.yml",
        ),
        (
            "foo/bar/.github/workflows/nested@evil.yml@refs/heads/main",
            "nested@evil.yml",
        ),
        (
            "foo/bar/.github/workflows/nested.yml@evil.yml@refs/heads/main",
            "nested.yml@evil.yml",
        ),
        (
            "foo/bar/.github/workflows/extra@nested.yml@evil.yml@refs/heads/main",
            "extra@nested.yml@evil.yml",
        ),
        (
            "foo/bar/.github/workflows/extra.yml@nested.yml@evil.yml@refs/heads/main",
            "extra.yml@nested.yml@evil.yml",
        ),
        (
            "foo/bar/.github/workflows/basic.yml@refs/heads/misleading@branch.yml",
            "basic.yml",
        ),
        (
            "foo/bar/.github/workflows/basic.yml@refs/heads/bad@branch@twomatches.yml",
            "basic.yml",
        ),
        ("foo/bar/.github/workflows/foo.yml.yml@refs/heads/main", "foo.yml.yml"),
        (
            "foo/bar/.github/workflows/foo.yml.foo.yml@refs/heads/main",
            "foo.yml.foo.yml",
        ),
        # Malformed workflow refs.
        ("foo/bar/.github/workflows/basic.wrongsuffix@refs/heads/main", None),
        ("foo/bar/.github/workflows/@refs/heads/main", None),
        ("foo/bar/.github/workflows/nosuffix@refs/heads/main", None),
        ("foo/bar/.github/workflows/.yml@refs/heads/main", None),
        ("foo/bar/.github/workflows/.yaml@refs/heads/main", None),
        ("foo/bar/.github/workflows/main.yml", None),
    ],
)
def test_extract_workflow_filename(workflow_ref, expected):
    assert github._extract_workflow_filename(workflow_ref) == expected


@pytest.mark.parametrize("claim", ["", "repo", "repo:"])
def test_check_sub(claim):
    assert github._check_sub(pretend.stub(), claim, pretend.stub()) is False


class TestGitHubPublisher:
    @pytest.mark.parametrize("environment", [None, "some_environment"])
    def test_lookup_fails_invalid_workflow_ref(self, environment):
        signed_claims = {
            "repository": "foo/bar",
            "job_workflow_ref": ("foo/bar/.github/workflows/.yml@refs/heads/main"),
            "repository_owner_id": "1234",
        }

        if environment:
            signed_claims["environment"] = environment

        # The `job_workflow_ref` is malformed, so no queries are performed.
        with pytest.raises(
            errors.InvalidPublisherError,
            match="Could not job extract workflow filename from OIDC claims",
        ):
            github.GitHubPublisher.lookup_by_claims(pretend.stub(), signed_claims)

    @pytest.mark.parametrize("environment", ["", "some_environment"])
    @pytest.mark.parametrize(
        ("workflow_a", "workflow_b"),
        [
            ("release-pypi.yml", "release_pypi.yml"),
            ("release%pypi.yml", "release-pypi.yml"),
        ],
    )
    def test_lookup_escapes(self, db_request, environment, workflow_a, workflow_b):
        GitHubPublisherFactory(
            id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            repository_owner="foo",
            repository_name="bar",
            repository_owner_id="1234",
            workflow_filename=workflow_a,
            environment=environment,
        )
        GitHubPublisherFactory(
            id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            repository_owner="foo",
            repository_name="bar",
            repository_owner_id="1234",
            workflow_filename=workflow_b,
            environment=environment,
        )

        for workflow in (workflow_a, workflow_b):
            signed_claims = {
                "repository": "foo/bar",
                "job_workflow_ref": (
                    f"foo/bar/.github/workflows/{workflow}@refs/heads/main"
                ),
                "repository_owner_id": "1234",
            }

            if environment:
                signed_claims["environment"] = environment

            assert (
                github.GitHubPublisher.lookup_by_claims(
                    db_request.db, signed_claims
                ).workflow_filename
                == workflow
            )

    def test_lookup_no_matching_publishers(self, db_request):
        GitHubPublisherFactory(
            id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            repository_owner="foo",
            repository_name="bar",
            repository_owner_id="1234",
            workflow_filename="release.yml",
            environment="environment",
        )
        signed_claims = {
            "repository": "foo/bar",
            "job_workflow_ref": (
                "foo/bar/.github/workflows/release.yml@refs/heads/main"
            ),
            "repository_owner_id": "1234",
            "environment": "another_environment",
        }

        with pytest.raises(errors.InvalidPublisherError) as e:
            github.GitHubPublisher.lookup_by_claims(db_request.db, signed_claims)
        assert str(e.value) == "Publisher with matching claims was not found"

    def test_github_publisher_all_known_claims(self):
        assert github.GitHubPublisher.all_known_claims() == {
            # required verifiable claims
            "sub",
            "repository",
            "repository_owner",
            "repository_owner_id",
            "job_workflow_ref",
            # required unverifiable claims
            "ref",
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
            "actor",
            "actor_id",
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
            "enterprise_id",
            "ref_protected",
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
        assert publisher.publisher_base_url == "https://github.com/fakeowner/fakerepo"
        assert publisher.publisher_url() == "https://github.com/fakeowner/fakerepo"
        assert (
            publisher.publisher_url({"sha": "somesha"})
            == "https://github.com/fakeowner/fakerepo/commit/somesha"
        )
        assert publisher.stored_claims({"sha": "somesha", "ref": "someref"}) == {
            "sha": "somesha",
            "ref": "someref",
        }

    def test_github_publisher_unaccounted_claims(self, monkeypatch):
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
            for claim_name in github.GitHubPublisher.all_known_claims()
        }
        signed_claims["fake-claim"] = "fake"
        signed_claims["another-fake-claim"] = "also-fake"

        github.GitHubPublisher.check_claims_existence(signed_claims)
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "JWT for GitHubPublisher has unaccounted claims: "
                "['another-fake-claim', 'fake-claim']"
            )
        ]
        assert scope.fingerprint == ["another-fake-claim", "fake-claim"]

    @pytest.mark.parametrize(
        "missing",
        github.GitHubPublisher.__required_verifiable_claims__.keys()
        | github.GitHubPublisher.__required_unverifiable_claims__,
    )
    def test_github_publisher_missing_claims(self, monkeypatch, missing):
        publisher = github.GitHubPublisher(
            repository_name="fakerepo",
            repository_owner="fakeowner",
            repository_owner_id="fakeid",
            workflow_filename="fakeworkflow.yml",
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
            for claim_name in github.GitHubPublisher.all_known_claims()
        }
        # Pop the missing claim, so that it's missing.
        signed_claims.pop(missing)
        assert missing not in signed_claims
        assert publisher.__required_verifiable_claims__
        with pytest.raises(errors.InvalidPublisherError) as e:
            github.GitHubPublisher.check_claims_existence(signed_claims)
        assert str(e.value) == f"Missing claim {missing!r}"
        assert sentry_sdk.capture_message.calls == [
            pretend.call(f"JWT for GitHubPublisher is missing claim: {missing}")
        ]
        assert scope.fingerprint == [missing]

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

        service_ = pretend.stub(
            jwt_identifier_exists=pretend.call_recorder(lambda s: False),
        )

        signed_claims = {
            claim_name: getattr(publisher, claim_name)
            for claim_name in github.GitHubPublisher.__required_verifiable_claims__
        }
        signed_claims["ref"] = "ref"
        signed_claims["sha"] = "sha"
        signed_claims["job_workflow_ref"] = publisher.job_workflow_ref + "@ref"
        assert publisher.__required_verifiable_claims__
        with pytest.raises(errors.InvalidPublisherError) as e:
            publisher.verify_claims(
                signed_claims=signed_claims, publisher_service=service_
            )
        assert str(e.value) == "Check failed for optional claim 'environment'"
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
            for claim_name in github.GitHubPublisher.all_known_claims()
            if claim_name not in missing_claims
        }
        github.GitHubPublisher.check_claims_existence(signed_claims)
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
            ("foo", None, False),
            ("", "", False),
            ("foo", "", False),
            # valid: exact and case-insensitive matches
            ("foo", "foo", True),
            ("Foo", "foo", True),
            ("Foo", "Foo", True),
            ("foo", "Foo", True),
            ("FOO", "foo", True),
            ("foo", "FOO", True),
        ],
    )
    def test_check_repository(self, truth, claim, valid):
        check = github.GitHubPublisher.__required_verifiable_claims__["repository"]
        assert check(truth, claim, pretend.stub()) == valid

    @pytest.mark.parametrize(
        ("claim", "ref", "sha", "valid", "expected"),
        [
            # okay: workflow name, followed by a nonempty ref
            (
                "foo/bar/.github/workflows/baz.yml@refs/tags/v0.0.1",
                "refs/tags/v0.0.1",
                "somesha",
                True,
                None,
            ),
            (
                "foo/bar/.github/workflows/baz.yml@refs/pulls/6",
                "refs/pulls/6",
                "somesha",
                True,
                None,
            ),
            (
                "foo/bar/.github/workflows/baz.yml@refs/heads/main",
                "refs/heads/main",
                "somesha",
                True,
                None,
            ),
            (
                "foo/bar/.github/workflows/baz.yml@notrailingslash",
                "notrailingslash",
                "somesha",
                True,
                None,
            ),
            # okay: workflow name, followed by a nonempty sha
            (
                "foo/bar/.github/workflows/baz.yml@somesha",
                "someref",
                "somesha",
                True,
                None,
            ),
            (
                "foo/bar/.github/workflows/baz.yml@somesha",
                None,
                "somesha",
                True,
                None,
            ),
            (
                "foo/bar/.github/workflows/baz.yml@somesha",
                "",
                "somesha",
                True,
                None,
            ),
            # bad: both ref and sha are missing
            (
                "foo/bar/.github/workflows/baz.yml@missing",
                None,
                None,
                False,
                "The ref and sha claims are empty",
            ),
            (
                "foo/bar/.github/workflows/baz.yml@missing",
                "",
                "",
                False,
                "The ref and sha claims are empty",
            ),
            # bad: workflow name with various attempted impersonations on the ref
            (
                "foo/bar/.github/workflows/baz.yml@fake.yml@notrailingslash",
                "somesha",
                "notrailingslash",
                False,
                "The job_workflow_ref claim does not match, expecting one of "
                "['foo/bar/.github/workflows/baz.yml@notrailingslash', "
                "'foo/bar/.github/workflows/baz.yml@somesha'], "
                "got 'foo/bar/.github/workflows/baz.yml@fake.yml@notrailingslash'",
            ),
            (
                "foo/bar/.github/workflows/baz.yml@fake.yml@refs/pulls/6",
                "somesha",
                "refs/pulls/6",
                False,
                "The job_workflow_ref claim does not match, expecting one of "
                "['foo/bar/.github/workflows/baz.yml@refs/pulls/6', "
                "'foo/bar/.github/workflows/baz.yml@somesha'], "
                "got 'foo/bar/.github/workflows/baz.yml@fake.yml@refs/pulls/6'",
            ),
            # bad: missing tail or workflow name or otherwise partial
            (
                "foo/bar/.github/workflows/baz.yml@",
                "somesha",
                "notrailingslash",
                False,
                "The job_workflow_ref claim does not match, expecting one of "
                "['foo/bar/.github/workflows/baz.yml@notrailingslash', "
                "'foo/bar/.github/workflows/baz.yml@somesha'], "
                "got 'foo/bar/.github/workflows/baz.yml@'",
            ),
            (
                "foo/bar/.github/workflows/@",
                "somesha",
                "notrailingslash",
                False,
                "The job_workflow_ref claim does not match, expecting one of "
                "['foo/bar/.github/workflows/baz.yml@notrailingslash', "
                "'foo/bar/.github/workflows/baz.yml@somesha'], "
                "got 'foo/bar/.github/workflows/@'",
            ),
            (
                "foo/bar/.github/workflows/",
                "somesha",
                "notrailingslash",
                False,
                "The job_workflow_ref claim does not match, expecting one of "
                "['foo/bar/.github/workflows/baz.yml@notrailingslash', "
                "'foo/bar/.github/workflows/baz.yml@somesha'], "
                "got 'foo/bar/.github/workflows/'",
            ),
            (
                "baz.yml",
                "somesha",
                "notrailingslash",
                False,
                "The job_workflow_ref claim does not match, expecting one of "
                "['foo/bar/.github/workflows/baz.yml@notrailingslash', "
                "'foo/bar/.github/workflows/baz.yml@somesha'], "
                "got 'baz.yml'",
            ),
            (
                "foo/bar/.github/workflows/baz.yml@malicious.yml@",
                "somesha",
                "notrailingslash",
                False,
                "The job_workflow_ref claim does not match, expecting one of "
                "['foo/bar/.github/workflows/baz.yml@notrailingslash', "
                "'foo/bar/.github/workflows/baz.yml@somesha'], "
                "got 'foo/bar/.github/workflows/baz.yml@malicious.yml@'",
            ),
            (
                "foo/bar/.github/workflows/baz.yml@@",
                "somesha",
                "notrailingslash",
                False,
                "The job_workflow_ref claim does not match, expecting one of "
                "['foo/bar/.github/workflows/baz.yml@notrailingslash', "
                "'foo/bar/.github/workflows/baz.yml@somesha'], "
                "got 'foo/bar/.github/workflows/baz.yml@@'",
            ),
            ("", None, None, False, "The job_workflow_ref claim is empty"),
        ],
    )
    def test_github_publisher_job_workflow_ref(self, claim, ref, sha, valid, expected):
        publisher = github.GitHubPublisher(
            repository_name="bar",
            repository_owner="foo",
            repository_owner_id=pretend.stub(),
            workflow_filename="baz.yml",
        )

        check = github.GitHubPublisher.__required_verifiable_claims__[
            "job_workflow_ref"
        ]
        claims = {"ref": ref, "sha": sha}
        if valid:
            assert check(publisher.job_workflow_ref, claim, claims) is True
        else:
            with pytest.raises(errors.InvalidPublisherError) as e:
                check(publisher.job_workflow_ref, claim, claims) is True
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
    def test_github_publisher_sub_claim(self, truth, claim, valid):
        check = github.GitHubPublisher.__required_verifiable_claims__["sub"]
        assert check(truth, claim, pretend.stub()) is valid

    @pytest.mark.parametrize(
        ("truth", "claim", "valid"),
        [
            ("", None, True),
            ("", "", True),
            ("", "some-environment", True),
            ("some-environment", "some-environment", True),
            ("some-environment", "sOmE-eNvIrOnMeNt", True),
            ("some-environment", None, False),
            ("some-environment", "some-other-environment", False),
        ],
    )
    def test_github_publisher_environment_claim(self, truth, claim, valid):
        check = github.GitHubPublisher.__optional_verifiable_claims__["environment"]
        assert check(truth, claim, pretend.stub()) is valid

    def test_github_publisher_duplicates_cant_be_created(self, db_request):
        publisher1 = github.GitHubPublisher(
            repository_name="repository_name",
            repository_owner="repository_owner",
            repository_owner_id="666",
            workflow_filename="workflow_filename.yml",
            environment="",
        )
        db_request.db.add(publisher1)
        db_request.db.commit()

        publisher2 = github.GitHubPublisher(
            repository_name="repository_name",
            repository_owner="repository_owner",
            repository_owner_id="666",
            workflow_filename="workflow_filename.yml",
            environment="",
        )
        db_request.db.add(publisher2)

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            db_request.db.commit()

    @pytest.mark.parametrize(
        "repository_name",
        [
            "repository_name",
            "Repository_Name",
        ],
    )
    @pytest.mark.parametrize(
        "repository_owner",
        [
            "repository_owner",
            "Repository_Owner",
        ],
    )
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://github.com/repository_owner/repository_name.git", True),
            ("https://github.com/repository_owner/repository_name.git/", True),
            ("https://github.com/repository_owner/repository_name.git/issues", False),
            ("https://repository_owner.github.io/repository_name/", True),
            ("https://repository_owner.github.io/repository_name", True),
            ("https://repository_owner.github.io/repository_name/subpage", True),
            ("https://repository_owner.github.io/repository_name/../malicious", False),
            ("https://repository_owner.github.io/", False),
            ("https://repository_owner.github.io/unrelated_name/", False),
            ("https://github.com/RePosItory_OwNeR/rePository_Name.git", True),
            ("https://repository_owner.github.io/RePoSiToRy_NaMe/subpage", True),
        ],
    )
    def test_github_publisher_verify_url(
        self, url, expected, repository_name, repository_owner
    ):
        publisher = github.GitHubPublisher(
            repository_name=repository_name,
            repository_owner=repository_owner,
            repository_owner_id="666",
            workflow_filename="workflow_filename.yml",
            environment="",
        )
        assert publisher.verify_url(url) == expected

    @pytest.mark.parametrize("environment", ["", "some-env"])
    def test_github_publisher_attestation_identity(self, environment):
        publisher = github.GitHubPublisher(
            repository_name="repository_name",
            repository_owner="repository_owner",
            repository_owner_id="666",
            workflow_filename="workflow_filename.yml",
            environment=environment,
        )

        identity = publisher.attestation_identity
        assert identity.repository == publisher.repository
        assert identity.workflow == publisher.workflow_filename

        if not environment:
            assert identity.environment is None
        else:
            assert identity.environment == publisher.environment

    @pytest.mark.parametrize("exists_in_db", [True, False])
    def test_exists(self, db_request, exists_in_db):
        publisher = github.GitHubPublisher(
            repository_name="repository_name",
            repository_owner="repository_owner",
            repository_owner_id="666",
            workflow_filename="workflow_filename.yml",
            environment="",
        )

        if exists_in_db:
            db_request.db.add(publisher)
            db_request.db.flush()

        assert publisher.exists(db_request.db) == exists_in_db


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
