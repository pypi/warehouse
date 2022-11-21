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

import faker
import pretend

from tests.common.db.packaging import ProjectFactory, ReleaseFactory
from warehouse.integrations.vulnerabilities import tasks


def test_analyze_vulnerability(db_request, metrics):
    project = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project, version="1.0")
    release2 = ReleaseFactory.create(project=project, version="2.0")
    release3 = ReleaseFactory.create(project=project, version="3.0")

    metrics_counter = collections.Counter()

    def metrics_increment(key, tags):
        metrics_counter.update([(key, tuple(tags))])

    metrics = pretend.stub(increment=metrics_increment, timed=metrics.timed)
    db_request.find_service = lambda *a, **kw: metrics

    tasks.analyze_vulnerability_task(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1.0", "2.0"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias1", "vuln_alias2"],
        },
        origin="test_report_source",
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
    db_request.find_service = lambda *a, **kw: metrics

    tasks.analyze_vulnerability_task(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1.0"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
    )

    assert len(release1.vulnerabilities) == 1
    assert len(release2.vulnerabilities) == 0
    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.processed", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
    }

    metrics_counter.clear()

    tasks.analyze_vulnerability_task(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1.0", "2.0"],  # Add 2.0
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
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
    db_request.find_service = lambda *a, **kw: metrics

    tasks.analyze_vulnerability_task(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1.0", "2.0"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
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

    tasks.analyze_vulnerability_task(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1.0"],  # Remove v2 as vulnerable
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
    )

    assert len(release1.vulnerabilities) == 1
    assert len(release2.vulnerabilities) == 0
    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.processed", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
    }

    metrics_counter.clear()

    tasks.analyze_vulnerability_task(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": [],  # Remove all releases
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
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
    db_request.find_service = lambda *a, **kw: metrics

    tasks.analyze_vulnerability_task(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1", "2"],
            # "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
    )

    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.error.format", ("origin:test_report_source",)): 1,
    }


def test_analyze_vulnerability_project_not_found(db_request, metrics):
    metrics_counter = collections.Counter()

    def metrics_increment(key, tags):
        metrics_counter.update([(key, tuple(tags))])

    metrics = pretend.stub(increment=metrics_increment, timed=metrics.timed)
    db_request.find_service = lambda *a, **kw: metrics

    tasks.analyze_vulnerability_task(
        request=db_request,
        vulnerability_report={
            "project": faker.Faker().text(max_nb_chars=8),
            "versions": ["1", "2"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
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
    db_request.find_service = lambda *a, **kw: metrics

    tasks.analyze_vulnerability_task(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": ["1", "2"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
    )

    assert metrics_counter == {
        (
            "warehouse.vulnerabilities.error.release_not_found",
            ("origin:test_report_source",),
        ): 2,
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
        (
            "warehouse.vulnerabilities.error.no_releases_found",
            ("origin:test_report_source",),
        ): 1,
        ("warehouse.vulnerabilities.processed", ("origin:test_report_source",)): 1,
    }


def test_analyze_vulnerability_no_versions(db_request, metrics):
    project = ProjectFactory.create()

    metrics_counter = collections.Counter()

    def metrics_increment(key, tags):
        metrics_counter.update([(key, tuple(tags))])

    metrics = pretend.stub(increment=metrics_increment, timed=metrics.timed)
    db_request.find_service = lambda *a, **kw: metrics

    tasks.analyze_vulnerability_task(
        request=db_request,
        vulnerability_report={
            "project": project.name,
            "versions": [],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        },
        origin="test_report_source",
    )

    assert metrics_counter == {
        ("warehouse.vulnerabilities.received", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.valid", ("origin:test_report_source",)): 1,
        ("warehouse.vulnerabilities.processed", ("origin:test_report_source",)): 1,
    }
