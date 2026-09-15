# SPDX-License-Identifier: Apache-2.0

import time

import pytest
import requests
import responses

from warehouse import integrations
from warehouse.integrations.vulnerabilities import osv


class TestVulnerabilityReportVerifier:
    def test_init(self, metrics, mocker):
        session = mocker.sentinel.session
        cache = integrations.PublicKeysCache(cache_time=12)

        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            session=session,
            metrics=metrics,
            public_keys_cache=cache,
        )

        # assert vuln_report_verifier._session is session
        assert vuln_report_verifier._metrics is metrics
        assert vuln_report_verifier._public_keys_cache is cache

    @responses.activate
    def test_verify_cache_miss(self, metrics, mocker):
        # Example taken from
        # https://gist.github.com/ewjoachim/7dde11c31d9686ed6b4431c3ca166da2
        meta_payload = {
            "public_keys": [
                {
                    "key_identifier": "90a421169f0a406205f1563a953312f0be898d3c"
                    "7b6c06b681aa86a874555f4a",
                    "key": "-----BEGIN PUBLIC KEY-----\n"
                    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE1c2S+CINXEihVeXz95He1bmWfhPc\n"
                    "ri7XBJXSEtW2IuZZyrlQP7wDXVupMZ3OsGsZaNX0SL4/nOx2S4OTrF1miA==\n"
                    "-----END PUBLIC KEY-----\n",
                    "is_current": True,
                }
            ]
        }
        responses.add(responses.GET, "http://foo", json=meta_payload)
        cache = integrations.PublicKeysCache(cache_time=12)
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=requests.Session(),
            metrics=metrics,
            public_keys_cache=cache,
        )
        key_id = "90a421169f0a406205f1563a953312f0be898d3c7b6c06b681aa86a874555f4a"
        signature = (
            "MEUCIQDz4wvDZjrX2YHsWhmu5Cvvp0gny6xYMD0AGrwEhTHGRAIgXCSvx"
            "Tl2SdnaY7fImXFRSKhbw3IRf68g1LMaQRetM80="
        )

        payload = (
            b'[{"project":"vuln_project",'
            b'"versions":["v1","v2"],'
            b'"id":"vuln_id",'
            b'"link":"vulns.com/vuln_id",'
            b'"aliases":["vuln_alias"]}]'
        )
        assert (
            vuln_report_verifier.verify(
                payload=payload, key_id=key_id, signature=signature
            )
            is True
        )

        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.vulnerabilities.osv.auth.cache.miss"),
            mocker.call("warehouse.vulnerabilities.osv.auth.success"),
        ]

    def test_verify_cache_hit(self, metrics, mocker):
        session = mocker.sentinel.session
        cache = integrations.PublicKeysCache(cache_time=12)
        cache.cached_at = time.time()
        cache.cache = [
            {
                "key_id": "90a421169f0a406205f1563a953312f0be898d3c"
                "7b6c06b681aa86a874555f4a",
                "key": "-----BEGIN PUBLIC KEY-----\n"
                "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE1c2S+CINXEihVeXz95He1bmWfhPc\n"
                "ri7XBJXSEtW2IuZZyrlQP7wDXVupMZ3OsGsZaNX0SL4/nOx2S4OTrF1miA==\n"
                "-----END PUBLIC KEY-----\n",
            }
        ]
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=session,
            metrics=metrics,
            public_keys_cache=cache,
        )

        key_id = "90a421169f0a406205f1563a953312f0be898d3c7b6c06b681aa86a874555f4a"
        signature = (
            "MEUCIQDz4wvDZjrX2YHsWhmu5Cvvp0gny6xYMD0AGrwEhTHGRAIgXCSvx"
            "Tl2SdnaY7fImXFRSKhbw3IRf68g1LMaQRetM80="
        )

        payload = (
            b'[{"project":"vuln_project",'
            b'"versions":["v1","v2"],'
            b'"id":"vuln_id",'
            b'"link":"vulns.com/vuln_id",'
            b'"aliases":["vuln_alias"]}]'
        )
        assert (
            vuln_report_verifier.verify(
                payload=payload, key_id=key_id, signature=signature
            )
            is True
        )

        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.vulnerabilities.osv.auth.cache.hit"),
            mocker.call("warehouse.vulnerabilities.osv.auth.success"),
        ]

    def test_verify_error(self, metrics, mocker):
        cache = integrations.PublicKeysCache(cache_time=12)
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=mocker.sentinel.session,
            metrics=metrics,
            public_keys_cache=cache,
        )
        mocker.patch.object(
            vuln_report_verifier,
            "retrieve_public_key_payload",
            side_effect=integrations.InvalidPayloadSignatureError("Bla", "bla"),
        )

        assert (
            vuln_report_verifier.verify(payload={}, key_id="a", signature="a") is False
        )

        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.vulnerabilities.osv.auth.cache.miss"),
            mocker.call("warehouse.vulnerabilities.osv.auth.error.bla"),
        ]

    @responses.activate
    def test_retrieve_public_key_payload(self, mocker):
        meta_payload = {
            "public_keys": [
                {
                    "key_identifier": "90a421169f0a406205f1563a953312f0be898d3c"
                    "7b6c06b681aa86a874555f4a",
                    "key": "-----BEGIN PUBLIC KEY-----\n"
                    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE1c2S+CINXEihVeXz95He1bmWfhPc\n"
                    "ri7XBJXSEtW2IuZZyrlQP7wDXVupMZ3OsGsZaNX0SL4/nOx2S4OTrF1miA==\n"
                    "-----END PUBLIC KEY-----\n",
                    "is_current": True,
                }
            ]
        }
        responses.add(responses.GET, "http://foo", json=meta_payload)

        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=requests.Session(),
            metrics=mocker.sentinel.metrics,
            public_keys_cache=mocker.sentinel.cache,
        )
        assert vuln_report_verifier.retrieve_public_key_payload() == meta_payload
        assert len(responses.calls) == 1
        assert responses.calls[0].request.url == "http://foo/"

    def test_get_cached_public_key_cache_hit(self, mocker):
        session = mocker.sentinel.session
        cache = integrations.PublicKeysCache(cache_time=12)
        cache_value = mocker.sentinel.cache_value
        cache.set(now=time.time(), value=cache_value)

        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=session,
            metrics=mocker.sentinel.metrics,
            public_keys_cache=cache,
        )

        assert vuln_report_verifier._get_cached_public_keys() is cache_value

    def test_get_cached_public_key_cache_miss_no_cache(self, mocker):
        session = mocker.sentinel.session
        cache = integrations.PublicKeysCache(cache_time=12)

        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=session,
            metrics=mocker.sentinel.metrics,
            public_keys_cache=cache,
        )

        with pytest.raises(integrations.CacheMissError):
            vuln_report_verifier._get_cached_public_keys()

    @responses.activate
    def test_retrieve_public_key_payload_http_error(self, mocker):
        responses.add(responses.GET, "http://foo", status=418, body="I'm a teapot")
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=requests.Session(),
            metrics=mocker.sentinel.metrics,
            public_keys_cache=mocker.sentinel.cache,
        )
        with pytest.raises(osv.OSVPublicKeyAPIError) as exc:
            vuln_report_verifier.retrieve_public_key_payload()

        assert str(exc.value) == "Invalid response code 418: I'm a teapot"
        assert exc.value.reason == "public_key_api.status.418"

    @responses.activate
    def test_retrieve_public_key_payload_json_error(self, mocker):
        responses.add(responses.GET, "http://foo", body="Still a non-json teapot")
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=requests.Session(),
            metrics=mocker.sentinel.metrics,
            public_keys_cache=mocker.sentinel.cache,
        )
        with pytest.raises(osv.OSVPublicKeyAPIError) as exc:
            vuln_report_verifier.retrieve_public_key_payload()

        assert str(exc.value) == "Non-JSON response received: Still a non-json teapot"
        assert exc.value.reason == "public_key_api.invalid_json"

    @responses.activate
    def test_retrieve_public_key_payload_connection_error(self, mocker):
        responses.add(responses.GET, "http://foo", body=requests.ConnectionError())

        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=requests.Session(),
            metrics=mocker.sentinel.metrics,
            public_keys_cache=mocker.sentinel.cache,
        )

        with pytest.raises(osv.OSVPublicKeyAPIError) as exc:
            vuln_report_verifier.retrieve_public_key_payload()

        assert str(exc.value) == "Could not connect to OSV"
        assert exc.value.reason == "public_key_api.network_error"

    def test_extract_public_keys(self, mocker):
        meta_payload = {
            "public_keys": [
                {
                    "key_identifier": "90a421169f0a406205f1563a953312f0be898d3c"
                    "7b6c06b681aa86a874555f4a",
                    "key": "-----BEGIN PUBLIC KEY-----\n"
                    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE1c2S+CINXEihVeXz95He1bmWfhPc\n"
                    "ri7XBJXSEtW2IuZZyrlQP7wDXVupMZ3OsGsZaNX0SL4/nOx2S4OTrF1miA==\n"
                    "-----END PUBLIC KEY-----\n",
                    "is_current": True,
                }
            ]
        }
        cache = integrations.PublicKeysCache(cache_time=12)
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=mocker.sentinel.session,
            metrics=mocker.sentinel.metrics,
            public_keys_cache=cache,
        )

        keys = vuln_report_verifier.extract_public_keys(pubkey_api_data=meta_payload)

        assert keys == [
            {
                "key": "-----BEGIN PUBLIC KEY-----\n"
                "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE1c2S+CINXEihVeXz95He1bmWfhPc\n"
                "ri7XBJXSEtW2IuZZyrlQP7wDXVupMZ3OsGsZaNX0SL4/nOx2S4OTrF1miA==\n"
                "-----END PUBLIC KEY-----\n",
                "key_id": "90a421169f0a406205f1563a953312f0be"
                "898d3c7b6c06b681aa86a874555f4a",
            }
        ]
        assert cache.cache == keys

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ([], "Payload is not a dict but: []"),
            ({}, "Payload misses 'public_keys' attribute"),
            ({"public_keys": None}, "Payload 'public_keys' attribute is not a list"),
            ({"public_keys": [None]}, "Key is not a dict but: None"),
            (
                {"public_keys": [{}]},
                "Missing attribute in key: ['key', 'key_identifier']",
            ),
            (
                {"public_keys": [{"key": "a"}]},
                "Missing attribute in key: ['key_identifier']",
            ),
            (
                {"public_keys": [{"key_identifier": "a"}]},
                "Missing attribute in key: ['key']",
            ),
        ],
    )
    def test_extract_public_keys_error(self, payload, expected, mocker):
        cache = integrations.PublicKeysCache(cache_time=12)
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=mocker.sentinel.session,
            metrics=mocker.sentinel.metrics,
            public_keys_cache=cache,
        )

        with pytest.raises(osv.OSVPublicKeyAPIError) as exc:
            list(vuln_report_verifier.extract_public_keys(pubkey_api_data=payload))

        assert exc.value.reason == "public_key_api.format_error"
        assert str(exc.value) == expected
        assert cache.cache is None

    def test_check_public_key(self, mocker):
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=mocker.sentinel.session,
            metrics=mocker.sentinel.metrics,
            public_keys_cache=mocker.sentinel.cache,
        )

        keys = [
            {"key_id": "a", "key": "b"},
            {"key_id": "c", "key": "d"},
        ]
        assert (
            vuln_report_verifier._check_public_key(public_keys=keys, key_id="c") == "d"
        )

    def test_check_public_key_error(self, mocker):
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=mocker.sentinel.session,
            metrics=mocker.sentinel.metrics,
            public_keys_cache=mocker.sentinel.cache,
        )

        with pytest.raises(integrations.InvalidPayloadSignatureError) as exc:
            vuln_report_verifier._check_public_key(public_keys=[], key_id="c")

        assert str(exc.value) == "Key c not found in public keys"
        assert exc.value.reason == "wrong_key_id"

    def test_check_signature(self, mocker):
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=mocker.sentinel.session,
            metrics=mocker.sentinel.metrics,
            public_keys_cache=mocker.sentinel.cache,
        )
        public_key = (
            "-----BEGIN PUBLIC KEY-----\n"
            "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE1c2S+CINXEihVeXz95He1bmWfhPc\n"
            "ri7XBJXSEtW2IuZZyrlQP7wDXVupMZ3OsGsZaNX0SL4/nOx2S4OTrF1miA==\n"
            "-----END PUBLIC KEY-----\n"
        )
        signature = (
            "MEUCIQDz4wvDZjrX2YHsWhmu5Cvvp0gny6xYMD0AGrwEhTHGRAIgXCSvx"
            "Tl2SdnaY7fImXFRSKhbw3IRf68g1LMaQRetM80="
        )
        payload = (
            b'[{"project":"vuln_project",'
            b'"versions":["v1","v2"],'
            b'"id":"vuln_id",'
            b'"link":"vulns.com/vuln_id",'
            b'"aliases":["vuln_alias"]}]'
        )
        assert (
            vuln_report_verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )
            is None
        )

    def test_check_signature_invalid_signature(self, mocker):
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=mocker.sentinel.session,
            metrics=mocker.sentinel.metrics,
            public_keys_cache=mocker.sentinel.cache,
        )
        public_key = (
            "-----BEGIN PUBLIC KEY-----\n"
            "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE1c2S+CINXEihVeXz95He1bmWfhPc\n"
            "ri7XBJXSEtW2IuZZyrlQP7wDXVupMZ3OsGsZaNX0SL4/nOx2S4OTrF1miA==\n"
            "-----END PUBLIC KEY-----\n"
        )
        signature = (
            "MEUCIQDz4wvDZjrX2YHsWd34db33f0gny6xYMD0AGrwEhTHGRAIgXCSvx"
            "Tl2SdnaY7fImXFRSKhbw3IRf68g1LMaQRetM80="
        )
        payload = (
            b'[{"project":"vuln_project",'
            b'"versions":["v1","v2"],'
            b'"id":"vuln_id",'
            b'"link":"vulns.com/vuln_id",'
            b'"aliases":["vuln_alias"]}]'
        )
        with pytest.raises(integrations.InvalidPayloadSignatureError) as exc:
            vuln_report_verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )

        assert str(exc.value) == "Invalid signature"
        assert exc.value.reason == "invalid_signature"

    def test_check_signature_invalid_crypto(self, mocker):
        vuln_report_verifier = osv.VulnerabilityReportVerifier(
            public_keys_api_url="http://foo",
            session=mocker.sentinel.session,
            metrics=mocker.sentinel.metrics,
            public_keys_cache=mocker.sentinel.cache,
        )
        public_key = ""
        signature = ""

        payload = "yeah, nope, that won't pass"

        with pytest.raises(integrations.InvalidPayloadSignatureError) as exc:
            vuln_report_verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )

        assert str(exc.value) == "Invalid cryptographic values"
        assert exc.value.reason == "invalid_crypto"
