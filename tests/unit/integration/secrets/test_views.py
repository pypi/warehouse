# SPDX-License-Identifier: Apache-2.0

import json

import pretend
import pytest

from webob.headers import EnvironHeaders

from warehouse.integrations.secrets import config, utils, views


class TestDiscloseToken:
    @pytest.mark.parametrize(
        ("origin", "headers", "settings", "api_url", "api_token"),
        [
            (
                config._github_origin,
                {
                    "GITHUB-PUBLIC-KEY-IDENTIFIER": "foo",
                    "GITHUB-PUBLIC-KEY-SIGNATURE": "bar",
                },
                {
                    "github.token": "token",
                },
                "https://api.github.com/meta/public_keys/token_scanning",
                "token",
            ),
            (
                config._github_origin,
                {  # Test for case-insensitivity on header names
                    "GitHub-Public-Key-Identifier": "foo",
                    "GitHub-Public-Key-Signature": "bar",
                },
                {
                    "github.token": "token",
                },
                "https://api.github.com/meta/public_keys/token_scanning",
                "token",
            ),
            (
                config._depsdev_origin,
                {
                    "GOSST-PUBLIC-KEY-IDENTIFIER": "foo",
                    "GOSST-PUBLIC-KEY-SIGNATURE": "bar",
                },
                {},
                "https://storage.googleapis.com/depsdev-gcp-public-keys/secret_scanning",  # noqa
                None,
            ),
        ],
    )
    def test_disclose_token(
        self,
        pyramid_request,
        metrics,
        monkeypatch,
        origin,
        headers,
        settings,
        api_url,
        api_token,
    ):
        pyramid_request.headers = EnvironHeaders({})
        for k, v in headers.items():
            pyramid_request.headers[k] = v
        pyramid_request.body = "[1, 2, 3]"
        pyramid_request.json_body = [1, 2, 3]
        pyramid_request.registry.settings = settings
        pyramid_request.find_service = lambda *a, **k: metrics

        http = pyramid_request.http = pretend.stub()

        verify = pretend.call_recorder(lambda **k: True)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(utils, "GenericTokenScanningPayloadVerifier", verifier_cls)

        analyze_disclosures = pretend.call_recorder(lambda **k: None)
        monkeypatch.setattr(utils, "analyze_disclosures", analyze_disclosures)

        response = views.disclose_token(pyramid_request)

        assert response.status_code == 204
        assert verifier_cls.calls == [
            pretend.call(
                session=http,
                metrics=metrics,
                origin=origin,
                api_token=api_token,
                api_url=api_url,
            )
        ]
        assert verify.calls == [
            pretend.call(payload="[1, 2, 3]", key_id="foo", signature="bar")
        ]
        assert analyze_disclosures.calls == [
            pretend.call(
                request=pyramid_request,
                disclosure_records=[1, 2, 3],
                origin=origin,
                metrics=metrics,
            )
        ]

    @pytest.mark.parametrize(
        ("headers"),
        [
            {
                "GITHUB-PUBLIC-KEY-IDENTIFIER": "foo",
                "GITHUB-PUBLIC-KEY-SIGNATURE": "bar",
            },
        ],
    )
    def test_disclose_token_no_token(
        self, pyramid_request, metrics, monkeypatch, headers
    ):
        pyramid_request.headers = headers
        pyramid_request.body = "[1, 2, 3]"
        pyramid_request.json_body = [1, 2, 3]
        pyramid_request.find_service = lambda *a, **k: metrics
        pyramid_request.http = pretend.stub()

        verify = pretend.call_recorder(lambda **k: True)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(utils, "GenericTokenScanningPayloadVerifier", verifier_cls)

        analyze_disclosures = pretend.call_recorder(lambda **k: None)
        monkeypatch.setattr(utils, "analyze_disclosures", analyze_disclosures)

        response = views.disclose_token(pyramid_request)

        assert response.status_code == 204

    @pytest.mark.parametrize(
        ("headers", "settings"),
        [
            (
                {
                    "GITHUB-PUBLIC-KEY-IDENTIFIER": "foo",
                    "GITHUB-PUBLIC-KEY-SIGNATURE": "bar",
                },
                {
                    "github.token": "token",
                },
            ),
        ],
    )
    def test_disclose_token_verify_fail(
        self, pyramid_request, metrics, monkeypatch, headers, settings
    ):
        pyramid_request.headers = headers
        pyramid_request.body = "[1, 2, 3]"
        pyramid_request.find_service = lambda *a, **k: metrics
        pyramid_request.registry.settings = settings
        pyramid_request.http = pretend.stub()

        verify = pretend.call_recorder(lambda **k: False)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(utils, "GenericTokenScanningPayloadVerifier", verifier_cls)

        response = views.disclose_token(pyramid_request)

        assert response.status_int == 400

    @pytest.mark.parametrize(
        ("origin", "headers", "settings"),
        [
            (
                "GitHub",
                {
                    "GITHUB-PUBLIC-KEY-IDENTIFIER": "foo",
                    "GITHUB-PUBLIC-KEY-SIGNATURE": "bar",
                },
                {
                    "github.token": "token",
                },
            ),
        ],
    )
    def test_disclose_token_verify_invalid_json(
        self, metrics, monkeypatch, origin, headers, settings
    ):
        verify = pretend.call_recorder(lambda **k: True)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(utils, "GenericTokenScanningPayloadVerifier", verifier_cls)

        # We need to raise on a property access, can't do that with a stub.
        class Request:

            def __init__(self, headers, body):
                self.headers = headers
                self.body = body

            @property
            def json_body(self):
                return json.loads(self.body)

            def find_service(self, *a, **k):
                return metrics

            response = pretend.stub(status_int=200)
            http = pretend.stub()
            registry = pretend.stub(settings=settings)

        request = Request(headers, "[")
        response = views.disclose_token(request)

        assert response.status_int == 400
        assert metrics.increment.calls == [
            pretend.call(
                f"warehouse.token_leak.{origin.lower()}.error.payload.json_error"
            )
        ]

    @pytest.mark.parametrize(
        ("origin", "headers", "settings"),
        [
            (
                "GitHub",
                {
                    "GITHUB-PUBLIC-KEY-IDENTIFIER": "foo",
                    "GITHUB-PUBLIC-KEY-SIGNATURE": "bar",
                },
                {
                    "github.token": "token",
                },
            ),
        ],
    )
    def test_disclose_token_wrong_payload(
        self, pyramid_request, metrics, monkeypatch, origin, headers, settings
    ):
        pyramid_request.headers = headers
        pyramid_request.body = "{}"
        pyramid_request.json_body = {}
        pyramid_request.registry.settings = settings
        pyramid_request.find_service = lambda *a, **k: metrics

        pyramid_request.http = pretend.stub()

        verify = pretend.call_recorder(lambda **k: True)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(utils, "GenericTokenScanningPayloadVerifier", verifier_cls)

        response = views.disclose_token(pyramid_request)

        assert response.status_code == 400
        assert metrics.increment.calls == [
            pretend.call(f"warehouse.token_leak.{origin.lower()}.error.format")
        ]

    def test_disclose_token_missing_headers(self, pyramid_request):
        response = views.disclose_token(pyramid_request)

        assert response.status_code == 404
