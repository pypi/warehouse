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
    "builder": "pypi_builder",
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
    "Jwcm9qZWN0IjoiZmFrZXByb2plY3QiLCJidWlsZGVyIjoicHlwaV9idWlsZGVyIiwiaW5"
    "ncmVkaWVudF9uYW1lIjoiZmFrZWluZ3JlZGllbnQiLCJhcnRpZmFjdF9pZCI6IjllNjdi"
    "MWNiLTJiOGQtNGJlNS05MWNiLTc1N2VkYjJlYzk3MCIsImlzcyI6Imh0dHBzOi8vcGxhd"
    "GZvcm0uYWN0aXZlc3RhdGUuY29tL2FwaS92MS9vYXV0aC9vaWRjIiwibmJmIjoxNjUwNj"
    "YzMjY1LCJleHAiOjE2NTA2NjQxNjUsImlhdCI6MTY1MDY2Mzg2NX0.R4q-vWAFXHrBSBK"
    "AZuHHIsGOkqlirPxEtLfjLIDiLr0"
)
