# SPDX-License-Identifier: Apache-2.0

import pretend

from celery.schedules import crontab

from warehouse.accounts.models import User
from warehouse.packaging.models import File, Project, Release
from warehouse.utils import row_counter

from ...common.db.packaging import FileFactory, ProjectFactory, ReleaseFactory


def test_compute_row_counts(db_request):
    project1 = ProjectFactory()
    project2 = ProjectFactory()
    release1 = ReleaseFactory(project=project1)
    release2 = ReleaseFactory(project=project2)
    release3 = ReleaseFactory(project=project2)
    FileFactory(release=release1)
    FileFactory(release=release2)
    FileFactory(release=release3, packagetype="sdist")
    FileFactory(release=release3, packagetype="bdist_wheel")

    counts = dict(
        db_request.db.query(row_counter.RowCount.table_name, row_counter.RowCount.count)
        .filter(
            row_counter.RowCount.table_name.in_(
                [
                    Project.__tablename__,
                    Release.__tablename__,
                    File.__tablename__,
                    User.__tablename__,
                ]
            )
        )
        .all()
    )

    assert counts == {"users": 0, "projects": 0, "releases": 0, "release_files": 0}

    row_counter.compute_row_counts(db_request)

    counts = dict(
        db_request.db.query(row_counter.RowCount.table_name, row_counter.RowCount.count)
        .filter(
            row_counter.RowCount.table_name.in_(
                [
                    Project.__tablename__,
                    Release.__tablename__,
                    File.__tablename__,
                    User.__tablename__,
                ]
            )
        )
        .all()
    )

    assert counts == {"users": 3, "projects": 2, "releases": 3, "release_files": 4}


def test_includeme():
    config = pretend.stub(add_periodic_task=pretend.call_recorder(lambda c, f: None))
    row_counter.includeme(config)
    assert config.add_periodic_task.calls == [
        pretend.call(crontab(minute="*/5"), row_counter.compute_row_counts),
    ]
