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
from pretend import call, call_recorder, stub
from pyramid.httpexceptions import HTTPSeeOther

from warehouse.packaging.models import (
    Project, Release, Dependency, File, Role, JournalEntry
)
from warehouse.utils.project import confirm_project, remove_project

from ...common.db.accounts import UserFactory
from ...common.db.packaging import (
    DependencyFactory, FileFactory, ProjectFactory, ReleaseFactory,
    RoleFactory,
)


def test_confirm():
    project = stub(normalized_name='foobar')
    request = stub(
        POST={'confirm': 'foobar'},
        route_path=call_recorder(lambda *a, **kw: stub()),
        session=stub(flash=call_recorder(lambda *a, **kw: stub())),
    )

    confirm_project(project, request, fail_route='fail_route')

    assert request.route_path.calls == []
    assert request.session.flash.calls == []


def test_confirm_no_input():
    project = stub(normalized_name='foobar')
    request = stub(
        POST={'confirm': ''},
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
        call('Must confirm the request.', queue='error')
    ]


def test_confirm_incorrect_input():
    project = stub(normalized_name='foobar')
    request = stub(
        POST={'confirm': 'bizbaz'},
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
        call("'bizbaz' is not the same as 'foobar'", queue='error')
    ]


def test_remove_project(db_request):
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

    remove_project(project, db_request)

    assert db_request.session.flash.calls == [
        call(
            "Successfully deleted the project 'foo'.",
            queue="success"
        ),
    ]

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
    assert journal_entry.action == "remove"
    assert journal_entry.submitted_by == db_request.user
    assert journal_entry.submitted_from == db_request.remote_addr
