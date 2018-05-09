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

import pytest
from pretend import call, call_recorder, stub, raiser
from pyramid.httpexceptions import HTTPSeeOther

from warehouse.packaging.models import (
    Project, Release, Dependency, File, Role, JournalEntry
)
from warehouse.utils.project import (
    confirm_project,
    destroy_docs,
    remove_project,
    remove_documentation,
)

from ...common.db.accounts import UserFactory
from ...common.db.packaging import (
    DependencyFactory, FileFactory, ProjectFactory, ReleaseFactory,
    RoleFactory,
)


def test_confirm():
    project = stub(normalized_name='foobar')
    request = stub(
        POST={'confirm_project_name': 'foobar'},
        route_path=call_recorder(lambda *a, **kw: stub()),
        session=stub(flash=call_recorder(lambda *a, **kw: stub())),
    )

    confirm_project(project, request, fail_route='fail_route')

    assert request.route_path.calls == []
    assert request.session.flash.calls == []


def test_confirm_no_input():
    project = stub(normalized_name='foobar')
    request = stub(
        POST={'confirm_project_name': ''},
        route_path=call_recorder(lambda *a, **kw: '/the-redirect'),
        session=stub(flash=call_recorder(lambda *a, **kw: stub())),
    )

    with pytest.raises(HTTPSeeOther) as err:
        confirm_project(project, request, fail_route='fail_route')
        assert err.value == '/the-redirect'

    assert request.route_path.calls == [
        call('fail_route', project_name='foobar')
    ]
    assert request.session.flash.calls == [
        call('Must confirm the request', queue='error')
    ]


def test_confirm_incorrect_input():
    project = stub(normalized_name='foobar')
    request = stub(
        POST={'confirm_project_name': 'bizbaz'},
        route_path=call_recorder(lambda *a, **kw: '/the-redirect'),
        session=stub(flash=call_recorder(lambda *a, **kw: stub())),
    )

    with pytest.raises(HTTPSeeOther) as err:
        confirm_project(project, request, fail_route='fail_route')
        assert err.value == '/the-redirect'

    assert request.route_path.calls == [
        call('fail_route', project_name='foobar')
    ]
    assert request.session.flash.calls == [
        call(
            "Could not delete project - 'bizbaz' is not the same as 'foobar'",
            queue='error'
        )
    ]


@pytest.mark.parametrize(
    'flash',
    [True, False]
)
def test_remove_project(db_request, flash):
    user = UserFactory.create()
    project = ProjectFactory.create(name="foo")
    release = ReleaseFactory.create(project=project)
    FileFactory.create(
        name=project.name,
        version=release.version,
        filename="who cares",
    )
    RoleFactory.create(user=user, project=project)
    DependencyFactory.create(name=project.name, version=release.version)

    db_request.user = user
    db_request.remote_addr = "192.168.1.1"
    db_request.session = stub(flash=call_recorder(lambda *a, **kw: stub()))

    remove_project(project, db_request, flash=flash)

    if flash:
        assert db_request.session.flash.calls == [
            call(
                "Successfully deleted the project 'foo'",
                queue="success"
            ),
        ]
    else:
        assert db_request.session.flash.calls == []

    assert not (db_request.db.query(Role)
                             .filter(Role.project == project).count())
    assert not (db_request.db.query(File)
                             .filter(File.name == project.name).count())
    assert not (db_request.db.query(Dependency)
                             .filter(Dependency.name == project.name).count())
    assert not (db_request.db.query(Release)
                             .filter(Release.name == project.name).count())
    assert not (db_request.db.query(Project)
                             .filter(Project.name == project.name).count())

    journal_entry = (
        db_request.db.query(JournalEntry)
                     .filter(JournalEntry.name == "foo")
                     .one()
    )
    assert journal_entry.action == "remove project"
    assert journal_entry.submitted_by == db_request.user
    assert journal_entry.submitted_from == db_request.remote_addr


@pytest.mark.parametrize(
    'flash',
    [True, False]
)
def test_destroy_docs(db_request, flash):
    user = UserFactory.create()
    project = ProjectFactory.create(name="foo", has_docs=True)
    RoleFactory.create(user=user, project=project)

    db_request.user = user
    db_request.remote_addr = "192.168.1.1"
    db_request.session = stub(flash=call_recorder(lambda *a, **kw: stub()))
    remove_documentation_recorder = stub(
        delay=call_recorder(lambda *a, **kw: None)
    )
    db_request.task = call_recorder(
        lambda *a, **kw: remove_documentation_recorder
    )

    destroy_docs(project, db_request, flash=flash)

    journal_entry = (
        db_request.db.query(JournalEntry)
                     .filter(JournalEntry.name == "foo")
                     .one()
    )
    assert journal_entry.action == "docdestroy"
    assert journal_entry.submitted_by == db_request.user
    assert journal_entry.submitted_from == db_request.remote_addr

    assert not (db_request.db.query(Project)
                             .filter(Project.name == project.name)
                             .first().has_docs)

    assert remove_documentation_recorder.delay.calls == [
        call('foo')
    ]

    if flash:
        assert db_request.session.flash.calls == [
            call(
                "Successfully deleted docs for project 'foo'",
                queue="success"
            ),
        ]
    else:
        assert db_request.session.flash.calls == []


def test_remove_documentation(db_request):
    project = ProjectFactory.create(name="foo", has_docs=True)
    task = stub()
    service = stub(remove_by_prefix=call_recorder(lambda project_name: None))
    db_request.find_service = call_recorder(
        lambda interface, name=None: service
    )
    db_request.log = stub(info=call_recorder(lambda *a, **kw: None))

    remove_documentation(task, db_request, project.name)

    assert service.remove_by_prefix.calls == [
        call(project.name)
    ]

    assert db_request.log.info.calls == [
        call("Removing documentation for %s", project.name),
    ]


def test_remove_documentation_retry(db_request):
    project = ProjectFactory.create(name="foo", has_docs=True)
    task = stub(retry=call_recorder(lambda *a, **kw: None))
    service = stub(remove_by_prefix=raiser(Exception))
    db_request.find_service = call_recorder(
        lambda interface, name=None: service
    )
    db_request.log = stub(info=call_recorder(lambda *a, **kw: None))

    remove_documentation(task, db_request, project.name)

    assert len(task.retry.calls) == 1

    assert db_request.log.info.calls == [
        call("Removing documentation for %s", project.name),
    ]
