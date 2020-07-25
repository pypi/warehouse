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

import collections
import json

import pretend

from warehouse.integrations.github import utils, views


class TestGitHubDiscloseToken:
    def test_github_disclose_token(self, pyramid_request, monkeypatch):

        pyramid_request.headers = {
            "GITHUB-PUBLIC-KEY-IDENTIFIER": "foo",
            "GITHUB-PUBLIC-KEY-SIGNATURE": "bar",
        }
        metrics = pretend.stub()

        pyramid_request.body = "[1, 2, 3]"
        pyramid_request.json_body = [1, 2, 3]
        pyramid_request.registry.settings = {"github.token": "token"}
        pyramid_request.find_service = lambda *a, **k: metrics

        http = pyramid_request.http = pretend.stub()

        verify = pretend.call_recorder(lambda **k: True)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(utils, "GitHubTokenScanningPayloadVerifier", verifier_cls)

        analyze_disclosures = pretend.call_recorder(lambda **k: None)
        monkeypatch.setattr(utils, "analyze_disclosures", analyze_disclosures)

        response = views.github_disclose_token(pyramid_request)

        assert response.status_code == 204
        assert verifier_cls.calls == [
            pretend.call(session=http, metrics=metrics, api_token="token")
        ]
        assert verify.calls == [
            pretend.call(payload="[1, 2, 3]", key_id="foo", signature="bar")
        ]
        assert analyze_disclosures.calls == [
            pretend.call(disclosure_records=[1, 2, 3], origin="github", metrics=metrics)
        ]

    def test_github_disclose_token_verify_fail(self, monkeypatch, pyramid_request):

        pyramid_request.headers = {
            "GITHUB-PUBLIC-KEY-IDENTIFIER": "foo",
            "GITHUB-PUBLIC-KEY-SIGNATURE": "bar",
        }
        metrics = pretend.stub()

        pyramid_request.body = "[1, 2, 3]"
        pyramid_request.find_service = lambda *a, **k: metrics
        pyramid_request.registry.settings = {"github.token": "token"}

        pyramid_request.http = pretend.stub()

        verify = pretend.call_recorder(lambda **k: False)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(utils, "GitHubTokenScanningPayloadVerifier", verifier_cls)

        response = views.github_disclose_token(pyramid_request)

        assert response.status_int == 400

    def test_github_disclose_token_verify_invalid_json(self, monkeypatch):
        verify = pretend.call_recorder(lambda **k: True)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(utils, "GitHubTokenScanningPayloadVerifier", verifier_cls)

        metrics = collections.Counter()

        def metrics_increment(key):
            metrics.update([key])

        # We need to raise on a property access, can't do that with a stub.
        class Request:
            headers = {
                "GITHUB-PUBLIC-KEY-IDENTIFIER": "foo",
                "GITHUB-PUBLIC-KEY-SIGNATURE": "bar",
            }
            body = "["

            @property
            def json_body(self):
                return json.loads(self.body)

            def find_service(self, *a, **k):
                return pretend.stub(increment=metrics_increment)

            response = pretend.stub(status_int=200)
            http = pretend.stub()
            registry = pretend.stub(settings={"github.token": "token"})

        request = Request()
        response = views.github_disclose_token(request)

        assert response.status_int == 400
        assert metrics == {"warehouse.token_leak.github.error.payload.json_error": 1}

    def test_github_disclose_token_wrong_payload(self, pyramid_request, monkeypatch):
        pyramid_request.headers = {
            "GITHUB-PUBLIC-KEY-IDENTIFIER": "foo",
            "GITHUB-PUBLIC-KEY-SIGNATURE": "bar",
        }

        metrics = collections.Counter()

        def metrics_increment(key):
            metrics.update([key])

        metrics_service = pretend.stub(increment=metrics_increment)

        pyramid_request.body = "{}"
        pyramid_request.json_body = {}
        pyramid_request.registry.settings = {"github.token": "token"}
        pyramid_request.find_service = lambda *a, **k: metrics_service

        pyramid_request.http = pretend.stub()

        verify = pretend.call_recorder(lambda **k: True)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(utils, "GitHubTokenScanningPayloadVerifier", verifier_cls)

        response = views.github_disclose_token(pyramid_request)

        assert response.status_code == 400
        assert metrics == {"warehouse.token_leak.github.error.format": 1}
