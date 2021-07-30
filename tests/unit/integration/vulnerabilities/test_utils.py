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

import factory.fuzzy
import pretend
import pytest

from sqlalchemy.orm.exc import NoResultFound

from tests.common.db.packaging import ProjectFactory, ReleaseFactory
from warehouse.integrations import vulnerabilities
from warehouse.integrations.vulnerabilities import tasks, utils


def test_analyze_vulnerability(db_request, metrics):
    project = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project, version="1.0")
    release2 = ReleaseFactory.create(project=project, version="2.0")
    release3 = ReleaseFactory.create(project=project, version="3.0")

    metrics_counter = collections.Counter()

    def metrics_increment(key, tags):
        metrics_counter.update([(key, tuple(tags))])

    metrics = pretend.stub(increment=metrics_increment, timed=metrics.timed)

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1.0", "2.0"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias1", "vuln_alias2"],
        },
        origin="test_report_source",
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
    assert vuln_record.source == "test_report_source"
    assert vuln_record.id == "vuln_id"
    assert vuln_record.link == "vulns.com/vuln_id"
    assert len(vuln_record.aliases) == 2
    assert "vuln_alias1" in vuln_record.aliases
    assert "vuln_alias2" in vuln_record.aliases

    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.processed", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
    }


def test_analyze_vulnerability_add_release(db_request, metrics):
    project = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project, version="1.0")
    release2 = ReleaseFactory.create(project=project, version="2.0")

    metrics_counter = collections.Counter()

    def metrics_increment(key, tags):
        metrics_counter.update([(key, tuple(tags))])

    metrics = pretend.stub(increment=metrics_increment, timed=metrics.timed)

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1.0"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
        metrics=metrics,
    )

    assert len(release1.vulnerabilities) == 1
    assert len(release2.vulnerabilities) == 0
    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.processed", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
    }

    metrics_counter.clear()

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1.0", "2.0"],  # Add 2.0
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
        metrics=metrics,
    )

    assert len(release1.vulnerabilities) == 1
    assert len(release2.vulnerabilities) == 1
    assert release1.vulnerabilities[0] == release2.vulnerabilities[0]

    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.processed", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
    }


def test_analyze_vulnerability_delete_releases(db_request, metrics):
    project = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project, version="1.0")
    release2 = ReleaseFactory.create(project=project, version="2.0")

    metrics_counter = collections.Counter()

    def metrics_increment(key, tags):
        metrics_counter.update([(key, tuple(tags))])

    metrics = pretend.stub(increment=metrics_increment, timed=metrics.timed)

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1.0", "2.0"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
        metrics=metrics,
    )

    assert len(release1.vulnerabilities) == 1
    assert len(release2.vulnerabilities) == 1
    assert release1.vulnerabilities[0] == release2.vulnerabilities[0]

    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.processed", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
    }

    metrics_counter.clear()

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1.0"],  # Remove v2 as vulnerable
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
        metrics=metrics,
    )

    assert len(release1.vulnerabilities) == 1
    assert len(release2.vulnerabilities) == 0
    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.processed", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
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
        origin="test_report_source",
        metrics=metrics,
    )

    # Weird behavior, see:
    # https://docs.sqlalchemy.org/en/14/orm/cascades.html#notes-on-delete-deleting-objects-referenced-from-collections-and-scalar-relationships
    # assert len(release1.vulnerabilities) == 0
    assert len(release2.vulnerabilities) == 0
    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.processed", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
    }


def test_analyze_vulnerability_invalid_request(db_request, metrics):
    project = ProjectFactory.create()

    metrics_counter = collections.Counter()

    def metrics_increment(key, tags):
        metrics_counter.update([(key, tuple(tags))])

    metrics = pretend.stub(increment=metrics_increment, timed=metrics.timed)

    with pytest.raises(vulnerabilities.InvalidVulnerabilityReportRequest) as exc:
        utils.analyze_vulnerability(
            request=db_request,
            vulnerability_report={
                "project": project.name,
                "versions": ["1", "2"],
                # "id": "vuln_id",
                "link": "vulns.com/vuln_id",
                "aliases": ["vuln_alias"],
            },
            origin="test_report_source",
            metrics=metrics,
        )

    assert str(exc.value) == "Record is missing attribute(s): id"
    assert exc.value.reason == "format"
    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.error.format", ("origin:test_report_source",)): 1,
    }


def test_analyze_vulnerability_project_not_found(db_request, metrics):
    metrics_counter = collections.Counter()

    def metrics_increment(key, tags):
        metrics_counter.update([(key, tuple(tags))])

    metrics = pretend.stub(increment=metrics_increment, timed=metrics.timed)

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
            origin="test_report_source",
            metrics=metrics,
        )

    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
        (
            "warehouse.vulnerabilities.error.project_not_found",
            ("origin:test_report_source",),
        ): 1,
    }


def test_analyze_vulnerability_release_not_found(db_request, metrics):
    project = ProjectFactory.create()
    ReleaseFactory.create(project=project, version="1.0")

    metrics_counter = collections.Counter()

    def metrics_increment(key, tags):
        metrics_counter.update([(key, tuple(tags))])

    metrics = pretend.stub(increment=metrics_increment, timed=metrics.timed)

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
            origin="test_report_source",
            metrics=metrics,
        )

    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
        (
            "warehouse.vulnerabilities.error.release_not_found",
            ("origin:test_report_source",),
        ): 1,
    }


def test_analyze_vulnerability_no_versions(db_request, metrics):
    project = ProjectFactory.create()

    metrics_counter = collections.Counter()

    def metrics_increment(key, tags):
        metrics_counter.update([(key, tuple(tags))])

    metrics = pretend.stub(increment=metrics_increment, timed=metrics.timed)

    utils.analyze_vulnerability(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": [],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
        metrics=metrics,
    )

    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.processed", ("origin:test_report_source",)): 1,
    }


def test_analyze_vulnerability_unknown_error(db_request, monkeypatch, metrics):
    metrics_counter = collections.Counter()

    def metrics_increment(key, tags):
        metrics_counter.update([(key, tuple(tags))])

    metrics = pretend.stub(increment=metrics_increment, timed=metrics.timed)

    class UnknownError(Exception):
        pass

    def raise_unknown_err():
        raise UnknownError()

    vuln_report_from_api_request = pretend.call_recorder(
        lambda **k: raise_unknown_err()
    )
    vuln_report_cls = pretend.stub(from_api_request=vuln_report_from_api_request)
    monkeypatch.setattr(vulnerabilities, "VulnerabilityReportRequest", vuln_report_cls)

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
            origin="test_report_source",
            metrics=metrics,
        )

    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.error.unknown", ("origin:test_report_source",)): 1,
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
        pretend.call(vulnerability_report=1, origin="whatever"),
        pretend.call(vulnerability_report=2, origin="whatever"),
        pretend.call(vulnerability_report=3, origin="whatever"),
    ]
