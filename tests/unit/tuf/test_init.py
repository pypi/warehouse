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

import pretend

from tests.common.db.packaging import ProjectFactory, UserFactory
from warehouse import tuf
from warehouse.tuf.interfaces import ITUFService
from warehouse.tuf.services import rstuf_factory


def test_update_metadata_for_project(db_request, monkeypatch):
    delay = pretend.call_recorder(lambda *a: None)
    config = pretend.stub(
        registry=pretend.stub(settings={"rstuf.api_url": "http://rstuf"}),
        task=pretend.call_recorder(lambda *a: pretend.stub(delay=delay)),
    )

    project0 = ProjectFactory.create()
    user0 = UserFactory.create()

    session = pretend.stub(info={}, new={project0, user0}, dirty=set())

    tuf.update_metadata_for_project(config, session, pretend.stub())

    # calls only for Projects
    assert config.task.calls == [pretend.call(tuf.update_metadata)]
    assert delay.calls == [pretend.call(project0.id)]


def test_update_metadata_for_project_rstuf_disabled(db_request, monkeypatch):
    delay = pretend.call_recorder(lambda *a: None)
    config = pretend.stub(
        registry=pretend.stub(settings={}),
        task=pretend.call_recorder(lambda *a: pretend.stub(delay=delay)),
    )

    project0 = ProjectFactory.create()

    session = pretend.stub(info={}, new={project0}, dirty=set())

    tuf.update_metadata_for_project(config, session, pretend.stub())

    assert config.task.calls == []
    assert delay.calls == []


def test_includeme():
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
        maybe_dotted=pretend.call_recorder(lambda *a: "http://rstuf"),
    )

    tuf.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(rstuf_factory, ITUFService),
    ]
