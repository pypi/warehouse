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
import time

import factory.fuzzy
import pretend
import pytest
import requests

from sqlalchemy.orm.exc import NoResultFound

from tests.common.db.packaging import ProjectFactory, ReleaseFactory
from warehouse.integrations import verifier
from warehouse.integrations.vulnerabilities import tasks, utils


def test_invalid_vulnerability_report():
    exc = utils.InvalidVulnerabilityReportRequest("error string", "reason")

    assert str(exc) == "error string"
    assert exc.reason == "reason"


@pytest.mark.parametrize(
    "record, error, reason",
    [
        (None, "Record is not a dict but: None", "format"),
        (
            {},
            "Record is missing attribute(s): aliases, id, link, project, versions",
            "format",
        ),
    ],
)
def test_vulnerability_report_request_from_api_request_error(record, error, reason):

    with pytest.raises(utils.InvalidVulnerabilityReportRequest) as exc:
        utils.VulnerabilityReportRequest.from_api_request(record)

    assert str(exc.value) == error
    assert exc.value.reason == reason


def test_vulnerability_report_request_from_api_request():
    request = utils.VulnerabilityReportRequest.from_api_request(
        request={
            "project": "vuln_project",
            "versions": ["v1", "v2"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        }
    )

    assert request.project == "vuln_project"
    assert request.versions == ["v1", "v2"]
    assert request.vulnerability_id == "vuln_id"
    assert request.advisory_link == "vulns.com/vuln_id"
    assert request.aliases == ["vuln_alias"]


class TestVulnerabilityVerifier:
    def test_init(self):
        metrics = pretend.stub()
        session = pretend.stub()
        cache = verifier.PublicKeysCache(cache_time=12)

        vuln_verifier = utils.VulnerabilityVerifier(
            session=session,
            metrics=metrics,
            public_keys_cache=cache,
        )

        # assert vuln_verifier._session is session
        assert vuln_verifier._metrics is metrics
        assert vuln_verifier._public_keys_cache is cache

    def test_verify_cache_miss(self):
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
        response = pretend.stub(
            json=lambda: meta_payload, raise_for_status=lambda: None
        )
        session = pretend.stub(get=lambda *a, **k: response)
        metrics = pretend.stub(increment=pretend.call_recorder(lambda str: None))
        cache = verifier.PublicKeysCache(cache_time=12)
        vuln_verifier = utils.VulnerabilityVerifier(
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
            vuln_verifier.verify(payload=payload, key_id=key_id, signature=signature)
            is True
        )

        assert metrics.increment.calls == [
            pretend.call("warehouse.vulnerabilities.osv.auth.cache.miss"),
            pretend.call("warehouse.vulnerabilities.osv.auth.success"),
        ]

    def test_verify_cache_hit(self):
        session = pretend.stub()
        metrics = pretend.stub(increment=pretend.call_recorder(lambda str: None))
        cache = verifier.PublicKeysCache(cache_time=12)
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
        vuln_verifier = utils.VulnerabilityVerifier(
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
            vuln_verifier.verify(payload=payload, key_id=key_id, signature=signature)
            is True
        )

        assert metrics.increment.calls == [
            pretend.call("warehouse.vulnerabilities.osv.auth.cache.hit"),
            pretend.call("warehouse.vulnerabilities.osv.auth.success"),
        ]

    def test_verify_error(self):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda str: None))
        cache = verifier.PublicKeysCache(cache_time=12)
        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=pretend.stub(),
            metrics=metrics,
            public_keys_cache=cache,
        )
        vuln_verifier.retrieve_public_key_payload = pretend.raiser(
            verifier.InvalidPayloadSignature("Bla", "bla")
        )

        assert vuln_verifier.verify(payload={}, key_id="a", signature="a") is False

        assert metrics.increment.calls == [
            pretend.call("warehouse.vulnerabilities.osv.auth.cache.miss"),
            pretend.call("warehouse.vulnerabilities.osv.auth.error.bla"),
        ]

    def test_retrieve_public_key_payload(self):
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
        response = pretend.stub(
            json=lambda: meta_payload, raise_for_status=lambda: None
        )
        session = pretend.stub(get=pretend.call_recorder(lambda *a, **k: response))
        metrics = pretend.stub(increment=pretend.call_recorder(lambda str: None))

        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=session,
            metrics=metrics,
            public_keys_cache=pretend.stub(),
        )
        assert vuln_verifier.retrieve_public_key_payload() == meta_payload
        assert session.get.calls == [
            pretend.call(
                "http://foo",
            )
        ]

    def test_get_cached_public_key_cache_hit(self):
        metrics = pretend.stub()
        session = pretend.stub()
        cache = verifier.PublicKeysCache(cache_time=12)
        cache_value = pretend.stub()
        cache.set(now=time.time(), value=cache_value)

        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=session,
            metrics=metrics,
            public_keys_cache=cache,
        )

        assert vuln_verifier._get_cached_public_keys() is cache_value

    def test_get_cached_public_key_cache_miss_no_cache(self):
        metrics = pretend.stub()
        session = pretend.stub()
        cache = verifier.PublicKeysCache(cache_time=12)

        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=session,
            metrics=metrics,
            public_keys_cache=cache,
        )

        with pytest.raises(verifier.CacheMiss):
            vuln_verifier._get_cached_public_keys()

    def test_retrieve_public_key_payload_http_error(self):
        response = pretend.stub(
            status_code=418,
            text="I'm a teapot",
            raise_for_status=pretend.raiser(requests.HTTPError),
        )
        session = pretend.stub(
            get=lambda *a, **k: response,
        )
        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=session,
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )
        with pytest.raises(utils.OSVPublicKeyAPIError) as exc:
            vuln_verifier.retrieve_public_key_payload()

        assert str(exc.value) == "Invalid response code 418: I'm a teapot"
        assert exc.value.reason == "public_key_api.status.418"

    def test_retrieve_public_key_payload_json_error(self):
        response = pretend.stub(
            text="Still a non-json teapot",
            json=pretend.raiser(json.JSONDecodeError("", "", 3)),
            raise_for_status=lambda: None,
        )
        session = pretend.stub(get=lambda *a, **k: response)
        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=session,
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )
        with pytest.raises(utils.OSVPublicKeyAPIError) as exc:
            vuln_verifier.retrieve_public_key_payload()

        assert str(exc.value) == "Non-JSON response received: Still a non-json teapot"
        assert exc.value.reason == "public_key_api.invalid_json"

    def test_retrieve_public_key_payload_connection_error(self):
        session = pretend.stub(get=pretend.raiser(requests.ConnectionError))

        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=session,
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )

        with pytest.raises(utils.OSVPublicKeyAPIError) as exc:
            vuln_verifier.retrieve_public_key_payload()

        assert str(exc.value) == "Could not connect to GitHub"
        assert exc.value.reason == "public_key_api.network_error"

    def test_extract_public_keys(self):
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
        cache = verifier.PublicKeysCache(cache_time=12)
        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=cache,
        )

        keys = vuln_verifier.extract_public_keys(pubkey_api_data=meta_payload)

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
        "payload, expected",
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
    def test_extract_public_keys_error(self, payload, expected):
        cache = verifier.PublicKeysCache(cache_time=12)
        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=cache,
        )

        with pytest.raises(utils.OSVPublicKeyAPIError) as exc:
            list(vuln_verifier.extract_public_keys(pubkey_api_data=payload))

        assert exc.value.reason == "public_key_api.format_error"
        assert str(exc.value) == expected
        assert cache.cache is None

    def test_check_public_key(self):
        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )

        keys = [
            {"key_id": "a", "key": "b"},
            {"key_id": "c", "key": "d"},
        ]
        assert vuln_verifier._check_public_key(public_keys=keys, key_id="c") == "d"

    def test_check_public_key_error(self):
        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )

        with pytest.raises(verifier.InvalidPayloadSignature) as exc:
            vuln_verifier._check_public_key(public_keys=[], key_id="c")

        assert str(exc.value) == "Key c not found in public keys"
        assert exc.value.reason == "wrong_key_id"

    def test_check_signature(self):
        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
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
            vuln_verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )
            is None
        )

    def test_check_signature_invalid_signature(self):
        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
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
        with pytest.raises(verifier.InvalidPayloadSignature) as exc:
            vuln_verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )

        assert str(exc.value) == "Invalid signature"
        assert exc.value.reason == "invalid_signature"

    def test_check_signature_invalid_crypto(self):
        vuln_verifier = utils.VulnerabilityVerifier(
            public_keys_api_url="http://foo",
            session=pretend.stub(),
            metrics=pretend.stub(),
            public_keys_cache=pretend.stub(),
        )
        public_key = ""
        signature = ""

        payload = "yeah, nope, that won't pass"

        with pytest.raises(verifier.InvalidPayloadSignature) as exc:
            vuln_verifier._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )

        assert str(exc.value) == "Invalid cryptographic values"
        assert exc.value.reason == "invalid_crypto"


def test_analyze_vulnerability(db_request):
    project = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project, version="1.0")
    release2 = ReleaseFactory.create(project=project, version="2.0")
    release3 = ReleaseFactory.create(project=project, version="3.0")

    metrics_counter = collections.Counter()

    def metrics_increment(key):
        metrics_counter.update([key])

    metrics = pretend.stub(increment=metrics_increment)

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1", "2"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias1", "vuln_alias2"],
        },
        origin="osv",
        metrics=metrics,
    )

    assert len(release1.vulnerabilities) == 1
    assert len(release2.vulnerabilities) == 1
    assert len(release3.vulnerabilities) == 0
    assert release1.vulnerabilities[0] == release2.vulnerabilities[0]
    vuln_record = release1.vulnerabilities[0]
    assert len(vuln_record.releases) == 2
    assert release1 in vuln_record.releases
    assert release2 in vuln_record.releases
    assert vuln_record.source == "osv"
    assert vuln_record.id == "vuln_id"
    assert vuln_record.link == "vulns.com/vuln_id"
    assert len(vuln_record.aliases) == 2
    assert "vuln_alias1" in vuln_record.aliases
    assert "vuln_alias2" in vuln_record.aliases

    assert metrics_counter == {
        "warehouse.vulnerabilities.osv.received": 1,
        "warehouse.vulnerabilities.osv.processed": 1,
        "warehouse.vulnerabilities.osv.valid": 1,
    }


def test_analyze_vulnerability_add_release(db_request):
    project = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project, version="1.0")
    release2 = ReleaseFactory.create(project=project, version="2.0")

    metrics_counter = collections.Counter()

    def metrics_increment(key):
        metrics_counter.update([key])

    metrics = pretend.stub(increment=metrics_increment)

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="osv",
        metrics=metrics,
    )

    assert len(release1.vulnerabilities) == 1
    assert len(release2.vulnerabilities) == 0
    assert metrics_counter == {
        "warehouse.vulnerabilities.osv.received": 1,
        "warehouse.vulnerabilities.osv.processed": 1,
        "warehouse.vulnerabilities.osv.valid": 1,
    }

    metrics_counter.clear()

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1", "2"],  # Add v2
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="osv",
        metrics=metrics,
    )

    assert len(release1.vulnerabilities) == 1
    assert len(release2.vulnerabilities) == 1
    assert release1.vulnerabilities[0] == release2.vulnerabilities[0]

    assert metrics_counter == {
        "warehouse.vulnerabilities.osv.received": 1,
        "warehouse.vulnerabilities.osv.processed": 1,
        "warehouse.vulnerabilities.osv.valid": 1,
    }


def test_analyze_vulnerability_delete_releases(db_request):
    project = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project, version="1.0")
    release2 = ReleaseFactory.create(project=project, version="2.0")

    metrics_counter = collections.Counter()

    def metrics_increment(key):
        metrics_counter.update([key])

    metrics = pretend.stub(increment=metrics_increment)

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1", "2"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="osv",
        metrics=metrics,
    )

    assert len(release1.vulnerabilities) == 1
    assert len(release2.vulnerabilities) == 1
    assert release1.vulnerabilities[0] == release2.vulnerabilities[0]

    assert metrics_counter == {
        "warehouse.vulnerabilities.osv.received": 1,
        "warehouse.vulnerabilities.osv.processed": 1,
        "warehouse.vulnerabilities.osv.valid": 1,
    }

    metrics_counter.clear()

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1"],  # Remove v2 as vulnerable
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="osv",
        metrics=metrics,
    )

    assert len(release1.vulnerabilities) == 1
    assert len(release2.vulnerabilities) == 0
    assert metrics_counter == {
        "warehouse.vulnerabilities.osv.received": 1,
        "warehouse.vulnerabilities.osv.processed": 1,
        "warehouse.vulnerabilities.osv.valid": 1,
    }

    metrics_counter.clear()

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": [],  # Remove all releases
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="osv",
        metrics=metrics,
    )

    # Weird behavior, see:
    # https://docs.sqlalchemy.org/en/14/orm/cascades.html#notes-on-delete-deleting-objects-referenced-from-collections-and-scalar-relationships
    # assert len(release1.vulnerabilities) == 0
    assert len(release2.vulnerabilities) == 0
    assert metrics_counter == {
        "warehouse.vulnerabilities.osv.received": 1,
        "warehouse.vulnerabilities.osv.processed": 1,
        "warehouse.vulnerabilities.osv.valid": 1,
    }


def test_analyze_vulnerability_invalid_request(db_request):
    project = ProjectFactory.create()

    metrics_counter = collections.Counter()

    def metrics_increment(key):
        metrics_counter.update([key])

    metrics = pretend.stub(increment=metrics_increment)

    with pytest.raises(utils.InvalidVulnerabilityReportRequest) as exc:
        utils.analyze_vulnerability(
            request=db_request,
            vulnerability_report={
                "project": project.name,
                "versions": ["1", "2"],
                # "id": "vuln_id",
                "link": "vulns.com/vuln_id",
                "aliases": ["vuln_alias"],
            },
            origin="osv",
            metrics=metrics,
        )

    assert str(exc.value) == "Record is missing attribute(s): id"
    assert exc.value.reason == "format"
    assert metrics_counter == {
        "warehouse.vulnerabilities.osv.received": 1,
        "warehouse.vulnerabilities.osv.error.format": 1,
    }


def test_analyze_vulnerability_project_not_found(db_request):
    metrics_counter = collections.Counter()

    def metrics_increment(key):
        metrics_counter.update([key])

    metrics = pretend.stub(increment=metrics_increment)

    with pytest.raises(NoResultFound):
        utils.analyze_vulnerability(
            request=db_request,
            vulnerability_report={
                "project": factory.fuzzy.FuzzyText(length=8).fuzz(),
                "versions": ["1", "2"],
                "id": "vuln_id",
                "link": "vulns.com/vuln_id",
                "aliases": ["vuln_alias"],
            },
            origin="osv",
            metrics=metrics,
        )

    assert metrics_counter == {
        "warehouse.vulnerabilities.osv.received": 1,
        "warehouse.vulnerabilities.osv.valid": 1,
        "warehouse.vulnerabilities.osv.error.project_not_found": 1,
    }


def test_analyze_vulnerability_release_not_found(db_request):
    project = ProjectFactory.create()
    ReleaseFactory.create(project=project, version="1.0")

    metrics_counter = collections.Counter()

    def metrics_increment(key):
        metrics_counter.update([key])

    metrics = pretend.stub(increment=metrics_increment)

    with pytest.raises(NoResultFound):
        utils.analyze_vulnerability(
            request=db_request,
            vulnerability_report={
                "project": project.name,
                "versions": ["1", "2"],
                "id": "vuln_id",
                "link": "vulns.com/vuln_id",
                "aliases": ["vuln_alias"],
            },
            origin="osv",
            metrics=metrics,
        )

    assert metrics_counter == {
        "warehouse.vulnerabilities.osv.received": 1,
        "warehouse.vulnerabilities.osv.valid": 1,
        "warehouse.vulnerabilities.osv.error.release_not_found": 1,
    }


def test_analyze_vulnerability_no_versions(db_request):
    project = ProjectFactory.create()

    metrics_counter = collections.Counter()

    def metrics_increment(key):
        metrics_counter.update([key])

    metrics = pretend.stub(increment=metrics_increment)

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": [],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="osv",
        metrics=metrics,
    )

    assert metrics_counter == {
        "warehouse.vulnerabilities.osv.received": 1,
        "warehouse.vulnerabilities.osv.valid": 1,
        "warehouse.vulnerabilities.osv.processed": 1,
    }


def test_analyze_vulnerability_unknown_error(db_request, monkeypatch):
    metrics_counter = collections.Counter()

    def metrics_increment(key):
        metrics_counter.update([key])

    metrics = pretend.stub(increment=metrics_increment)

    class UnknownError(Exception):
        pass

    def raise_unknown_err():
        raise UnknownError()

    vuln_report_from_api_request = pretend.call_recorder(
        lambda **k: raise_unknown_err()
    )
    vuln_report_cls = pretend.stub(from_api_request=vuln_report_from_api_request)
    monkeypatch.setattr(utils, "VulnerabilityReportRequest", vuln_report_cls)

    with pytest.raises(UnknownError):
        utils.analyze_vulnerability(
            request=db_request,
            vulnerability_report={
                "project": "whatever",
                "versions": [],
                "id": "vuln_id",
                "link": "vulns.com/vuln_id",
                "aliases": ["vuln_alias"],
            },
            origin="osv",
            metrics=metrics,
        )

    assert metrics_counter == {
        "warehouse.vulnerabilities.osv.received": 1,
        "warehouse.vulnerabilities.osv.error.unknown": 1,
    }


def test_analyze_vulnerabilities(monkeypatch):
    task = pretend.stub(delay=pretend.call_recorder(lambda *a, **k: None))
    request = pretend.stub(task=lambda x: task)

    monkeypatch.setattr(tasks, "analyze_vulnerability_task", task)

    metrics = pretend.stub()

    utils.analyze_vulnerabilities(
        request=request,
        vulnerability_reports=[1, 2, 3],
        origin="whatever",
        metrics=metrics,
    )

    assert task.delay.calls == [
        pretend.call(vulnerability_report=1, origin="whatever", metrics=metrics),
        pretend.call(vulnerability_report=2, origin="whatever", metrics=metrics),
        pretend.call(vulnerability_report=3, origin="whatever", metrics=metrics),
    ]
