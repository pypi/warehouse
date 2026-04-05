# SPDX-License-Identifier: Apache-2.0

# Pytest Fixture Constants

REMOTE_ADDR = "1.2.3.4"

"""
Static output of `hashlib.sha256(REMOTE_ADDR.encode("utf8")).hexdigest()`
Created statically to prevent needing to calculate it every run.
"""
REMOTE_ADDR_HASHED = "6694f83c9f476da31f5df6bcc520034e7e57d421d247b9d34f49edbfc84a764c"

"""
Output of `hashlib.sha256((REMOTE_ADDR + "pepa").encode("utf8")).hexdigest()`
"""
REMOTE_ADDR_SALTED = "a69a49383d81404e4b1df297c7baa28e1cd6c4ee1495ed5d0ab165a63a147763"

"""
    {
    "jti": "6e67b1cb-2b8d-4be5-91cb-757edb2ec970",
    "sub": "repo:foo/bar",
    "aud": "pypi",
    "ref": "fake",
    "sha": "fake",
    "repository": "foo/bar",
    "repository_owner": "foo",
    "repository_owner_id": "123",
    "run_id": "fake",
    "run_number": "fake",
    "run_attempt": "1",
    "repository_id": "fake",
    "actor_id": "fake",
    "actor": "foo",
    "workflow": "fake",
    "head_ref": "fake",
    "base_ref": "fake",
    "event_name": "fake",
    "ref_type": "fake",
    "environment": "fake",
    "job_workflow_ref": "foo/bar/.github/workflows/example.yml@fake",
    "iss": "https://token.actions.githubusercontent.com",
    "nbf": 1650663265,
    "exp": 1650664165,
    "iat": 1650663865
    }
"""
DUMMY_GITHUB_OIDC_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI2ZTY3YjFjYi0yYjhkLTRiZ"
    "TUtOTFjYi03NTdlZGIyZWM5NzAiLCJzdWIiOiJyZXBvOmZvby9iYXIiLCJhdWQiOiJweXB"
    "pIiwicmVmIjoiZmFrZSIsInNoYSI6ImZha2UiLCJyZXBvc2l0b3J5IjoiZm9vL2JhciIsI"
    "nJlcG9zaXRvcnlfb3duZXIiOiJmb28iLCJyZXBvc2l0b3J5X293bmVyX2lkIjoiMTIzIiw"
    "icnVuX2lkIjoiZmFrZSIsInJ1bl9udW1iZXIiOiJmYWtlIiwicnVuX2F0dGVtcHQiOiIxI"
    "iwicmVwb3NpdG9yeV9pZCI6ImZha2UiLCJhY3Rvcl9pZCI6ImZha2UiLCJhY3RvciI6ImZ"
    "vbyIsIndvcmtmbG93IjoiZmFrZSIsImhlYWRfcmVmIjoiZmFrZSIsImJhc2VfcmVmIjoiZ"
    "mFrZSIsImV2ZW50X25hbWUiOiJmYWtlIiwicmVmX3R5cGUiOiJmYWtlIiwiZW52aXJvbm1"
    "lbnQiOiJmYWtlIiwiam9iX3dvcmtmbG93X3JlZiI6ImZvby9iYXIvLmdpdGh1Yi93b3JrZ"
    "mxvd3MvZXhhbXBsZS55bWxAZmFrZSIsImlzcyI6Imh0dHBzOi8vdG9rZW4uYWN0aW9ucy5"
    "naXRodWJ1c2VyY29udGVudC5jb20iLCJuYmYiOjE2NTA2NjMyNjUsImV4cCI6MTY1MDY2N"
    "DE2NSwiaWF0IjoxNjUwNjYzODY1fQ.f-FMv5FF5sdxAWeUilYDt9NoE7Et0vbdNhK32c2o"
    "C-E"
)

"""
    {
    "jti": "6e67b1cb-2b8d-4be5-91cb-757edb2ec970",
    "sub": "org:fakeorg:project:fakeproject",
    "aud": "pypi",
    "actor_id": "fake",
    "actor": "foo",
    "oraganization_id": "7e67b1cb-2b8d-4be5-91cb-757edb2ec970",
    "organization": "fakeorg",
    "project_visibility": "private",
    "project_id": "8e67b1cb-2b8d-4be5-91cb-757edb2ec970",
    "project_path": "fakeorg/fakeproject",
    "project": "fakeproject",
    "builder": "pypi-publisher",
    "ingredient_name": "fakeingredient",
    "artifact_id": "9e67b1cb-2b8d-4be5-91cb-757edb2ec970",
    "iss":"https://platform.activestate.com/api/v1/oauth/oidc",
    "nbf": 1650663265,
    "exp": 1650664165,
    "iat": 1650663865
    }
"""
DUMMY_ACTIVESTATE_OIDC_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI2ZTY3YjFjYi0yYjhkLTRi"
    "ZTUtOTFjYi03NTdlZGIyZWM5NzAiLCJzdWIiOiJvcmc6ZmFrZW9yZzpwcm9qZWN0OmZha"
    "2Vwcm9qZWN0IiwiYXVkIjoicHlwaSIsImFjdG9yX2lkIjoiZmFrZSIsImFjdG9yIjoiZm"
    "9vIiwib3JhZ2FuaXphdGlvbl9pZCI6IjdlNjdiMWNiLTJiOGQtNGJlNS05MWNiLTc1N2V"
    "kYjJlYzk3MCIsIm9yZ2FuaXphdGlvbiI6ImZha2VvcmciLCJwcm9qZWN0X3Zpc2liaWxp"
    "dHkiOiJwcml2YXRlIiwicHJvamVjdF9pZCI6IjhlNjdiMWNiLTJiOGQtNGJlNS05MWNiL"
    "Tc1N2VkYjJlYzk3MCIsInByb2plY3RfcGF0aCI6ImZha2VvcmcvZmFrZXByb2plY3QiLC"
    "Jwcm9qZWN0IjoiZmFrZXByb2plY3QiLCJidWlsZGVyIjoicHlwaS1wdWJsaXNoZXIiLC"
    "JpbmdyZWRpZW50X25hbWUiOiJmYWtlaW5ncmVkaWVudCIsImFydGlmYWN0X2lkIjoiOWU2"
    "N2IxY2ItMmI4ZC00YmU1LTkxY2ItNzU3ZWRiMmVjOTcwIiwiaXNzIjoiaHR0cHM6Ly9w"
    "bGF0Zm9ybS5hY3RpdmVzdGF0ZS5jb20vYXBpL3YxL29hdXRoL29pZGMiLCJuYmYiOjE2"
    "NTA2NjMyNjUsImV4cCI6MTY1MDY2NDE2NSwiaWF0IjoxNjUwNjYzODY1fQ.fakesig_acti"
    "vestate"
)

"""
    {
    "namespace_id": "123",
    "namespace_path": "foo",
    "project_id": "55235664",
    "project_path": "foo/bar",
    "user_id": "123",
    "user_login": "user",
    "user_email": "user@example.com",
    "user_access_level": "owner",
    "pipeline_id": "123",
    "pipeline_source": "push",
    "job_id": "123",
    "ref": "main",
    "ref_type": "branch",
    "ref_path": "refs/heads/main",
    "ref_protected": "true",
    "runner_id": 123,
    "runner_environment": "gitlab-hosted",
    "sha": "93969f556a29853b507bdcd9dec6b4217a4ea2e7",
    "project_visibility": "private",
    "ci_config_ref_uri": "gitlab.com/foo/bar//.gitlab-ci.yml@refs/heads/main",
    "ci_config_sha": "93969f556a29853b507bdcd9dec6b4217a4ea2e7",
    "jti": "2a5381a8-baf5-43c5-823d-544a08a067fb",
    "iat": 1750405794,
    "nbf": 1750405789,
    "exp": 1750409394,
    "iss": "https://gitlab.com",
    "sub": "project_path:foo/bar:ref_type:branch:ref:main",
    "aud": "pypi"
    }
"""
DUMMY_GITLAB_OIDC_JWT = (
    "eyJraWQiOiI0aTNzRkU3c3hxTlBPVDdGZHZjR0ExWlZHR0lfci10c0RYbkV1WVQ0WnFFI"
    "iwidHlwIjoiSldUIiwiYWxnIjoiUlMyNTYifQ.eyJuYW1lc3BhY2VfaWQiOiIxMjMiLCJ"
    "uYW1lc3BhY2VfcGF0aCI6ImZvbyIsInByb2plY3RfaWQiOiI1NTIzNTY2NCIsInByb2pl"
    "Y3RfcGF0aCI6ImZvby9iYXIiLCJ1c2VyX2lkIjoiMTIzIiwidXNlcl9sb2dpbiI6InVzZ"
    "XIiLCJ1c2VyX2VtYWlsIjoidXNlckBleGFtcGxlLmNvbSIsInVzZXJfYWNjZXNzX2xldm"
    "VsIjoib3duZXIiLCJwaXBlbGluZV9pZCI6IjEyMyIsInBpcGVsaW5lX3NvdXJjZSI6InB"
    "1c2giLCJqb2JfaWQiOiIxMjMiLCJyZWYiOiJtYWluIiwicmVmX3R5cGUiOiJicmFuY2gi"
    "LCJyZWZfcGF0aCI6InJlZnMvaGVhZHMvbWFpbiIsInJlZl9wcm90ZWN0ZWQiOiJ0cnVlI"
    "iwicnVubmVyX2lkIjoxMjMsInJ1bm5lcl9lbnZpcm9ubWVudCI6ImdpdGxhYi1ob3N0ZW"
    "QiLCJzaGEiOiI5Mzk2OWY1NTZhMjk4NTNiNTA3YmRjZDlkZWM2YjQyMTdhNGVhMmU3Iiw"
    "icHJvamVjdF92aXNpYmlsaXR5IjoicHJpdmF0ZSIsImNpX2NvbmZpZ19yZWZfdXJpIjoi"
    "Z2l0bGFiLmNvbS9mb28vYmFyLy8uZ2l0bGFiLWNpLnltbEByZWZzL2hlYWRzL21haW4iL"
    "CJjaV9jb25maWdfc2hhIjoiOTM5NjlmNTU2YTI5ODUzYjUwN2JkY2Q5ZGVjNmI0MjE3YT"
    "RlYTJlNyIsImp0aSI6IjJhNTM4MWE4LWJhZjUtNDNjNS04MjNkLTU0NGEwOGEwNjdmYiI"
    "sImlhdCI6MTc1MDQwNTc5NCwibmJmIjoxNzUwNDA1Nzg5LCJleHAiOjE3NTA0MDkzOTQs"
    "ImlzcyI6Imh0dHBzOi8vZ2l0bGFiLmNvbSIsInN1YiI6InByb2plY3RfcGF0aDpmb28vY"
    "mFyOnJlZl90eXBlOmJyYW5jaDpyZWY6bWFpbiIsImF1ZCI6InB5cGkifQ.g3ceS-5KkGC"
    "28nIKI-9HNf6lOPmBNyUAcQI-IjwZKpwcrWTcIM0lb6qKn1DyIqz2nE2W-SW3-hfZOIq9"
    "6xJhGuZfl2bAV7uj_WwUnEoh2hSqW99T2_2bqkrLqkwcJ2w5yvEE2WtzUsxpRqEmuhxHH"
    "uTOMLJPgydTqnJ2qe2oQxxWtpv_P0VjpZ_QXOk_KP6dBOHNdj7Iu7myCgybU5BTSyT33N"
    "kbWMiZHHBL6Andl3dU9eQD17-BYkuoQCzLxepoAzNKgiIRL3OULljfWP8wXcLymDXaj1Q"
    "A0sI9uulFYYx3ZgEmziSjv_e297kkrW3E_kbGyyGkTFxiOX6zSsKfUg"
)

"""
    {
    "namespace_id": "123",
    "namespace_path": "foo",
    "project_id": "55235664",
    "project_path": "foo/bar",
    "user_id": "123",
    "user_login": "user",
    "user_email": "user@example.com",
    "user_access_level": "owner",
    "pipeline_id": "123",
    "pipeline_source": "push",
    "job_id": "123",
    "ref": "main",
    "ref_type": "branch",
    "ref_path": "refs/heads/main",
    "ref_protected": "true",
    "runner_id": 123,
    "runner_environment": "self-hosted",
    "sha": "93969f556a29853b507bdcd9dec6b4217a4ea2e7",
    "project_visibility": "private",
    "ci_config_ref_uri": "gitlab.example.com/foo/bar//.gitlab-ci.yml@refs/heads/main",
    "ci_config_sha": "93969f556a29853b507bdcd9dec6b4217a4ea2e7",
    "jti": "3b6492c9-caf6-54d6-934e-655b19b178fc",
    "iat": 1750405794,
    "nbf": 1750405789,
    "exp": 1750409394,
    "iss": "https://gitlab.example.com",
    "sub": "project_path:foo/bar:ref_type:branch:ref:main",
    "aud": "pypi"
    }
"""
DUMMY_GITLAB_SELF_MANAGED_OIDC_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1lc3BhY2VfaWQiOiIxMjMiLCJuYW1l"
    "c3BhY2VfcGF0aCI6ImZvbyIsInByb2plY3RfaWQiOiI1NTIzNTY2NCIsInByb2plY3RfcGF0aCI"
    "6ImZvby9iYXIiLCJ1c2VyX2lkIjoiMTIzIiwidXNlcl9sb2dpbiI6InVzZXIiLCJ1c2VyX2Vt"
    "YWlsIjoidXNlckBleGFtcGxlLmNvbSIsInVzZXJfYWNjZXNzX2xldmVsIjoib3duZXIiLCJwa"
    "XBlbGluZV9pZCI6IjEyMyIsInBpcGVsaW5lX3NvdXJjZSI6InB1c2giLCJqb2JfaWQiOiIxMj"
    "MiLCJyZWYiOiJtYWluIiwicmVmX3R5cGUiOiJicmFuY2giLCJyZWZfcGF0aCI6InJlZnMvaGV"
    "hZHMvbWFpbiIsInJlZl9wcm90ZWN0ZWQiOiJ0cnVlIiwicnVubmVyX2lkIjoxMjMsInJ1bm5l"
    "cl9lbnZpcm9ubWVudCI6InNlbGYtaG9zdGVkIiwic2hhIjoiOTM5NjlmNTU2YTI5ODUzYjUwN"
    "2JkY2Q5ZGVjNmI0MjE3YTRlYTJlNyIsInByb2plY3RfdmlzaWJpbGl0eSI6InByaXZhdGUiLC"
    "JjaV9jb25maWdfcmVmX3VyaSI6ImdpdGxhYi5leGFtcGxlLmNvbS9mb28vYmFyLy8uZ2l0bGF"
    "iLWNpLnltbEByZWZzL2hlYWRzL21haW4iLCJjaV9jb25maWdfc2hhIjoiOTM5NjlmNTU2YTI5"
    "ODUzYjUwN2JkY2Q5ZGVjNmI0MjE3YTRlYTJlNyIsImp0aSI6IjNiNjQ5MmM5LWNhZjYtNTR"
    "kNi05MzRlLTY1NWIxOWIxNzhmYyIsImlhdCI6MTc1MDQwNTc5NCwibmJmIjoxNzUwNDA1Nzg5"
    "LCJleHAiOjE3NTA0MDkzOTQsImlzcyI6Imh0dHBzOi8vZ2l0bGFiLmV4YW1wbGUuY29tIiwi"
    "c3ViIjoicHJvamVjdF9wYXRoOmZvby9iYXI6cmVmX3R5cGU6YnJhbmNoOnJlZjptYWluIiwi"
    "YXVkIjoicHlwaSJ9.fakesig_for_testing_self_managed_gitlab"
)

"""
    {
    "iss": "https://accounts.google.com",
    "azp": "32555350559.apps.googleusercontent.com",
    "aud": "pypi",
    "sub": "111260650121185072906",
    "hd": "google.com",
    "email": "user@example.com",
    "email_verified": true,
    "at_hash": "_LLKKivfvfme9eoQ3WcMIg",
    "iat": 1650053185,
    "exp": 1650056785
}
"""
DUMMY_GOOGLE_OIDC_JWT = (
    "eyJhbGciOiJSUzI1NiIsImtpZCI6ImYxMzM4Y2EyNjgzNTg2M2Y2NzE0MDM5NDE3MzhhN"
    "2I0OWU3NDBmYzAiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmdv"
    "b2dsZS5jb20iLCJhenAiOiIzMjU1NTM1MDU1OS5hcHBzLmdvb2dsZXVzZXJjb250ZW50Lm"
    "NvbSIsImF1ZCI6InB5cGkiLCJzdWIiOiIxMTEyNjA2NTAxMjExODUwNzI5MDYiLCJoZCI6"
    "Imdvb2dsZS5jb20iLCJlbWFpbCI6InVzZXJAZXhhbXBsZS5jb20iLCJlbWFpbF92ZXJpZm"
    "llZCI6dHJ1ZSwiYXRfaGFzaCI6Il9MTEtLaXZmdmZtZTllb1EzV2NNSWciLCJpYXQiOjE2"
    "NTAwNTMxODUsImV4cCI6MTY1MDA1Njc4NX0.fakesig_google"
)
