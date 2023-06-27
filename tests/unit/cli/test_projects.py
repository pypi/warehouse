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

from warehouse.cli import projects
from warehouse.packaging.tasks import send_pep_715_notices


def test_notify_pep_715(cli):
    request = pretend.stub()
    task = pretend.stub(
        get_request=pretend.call_recorder(lambda: request),
        run=pretend.call_recorder(lambda r: None),
    )
    config = pretend.stub(task=pretend.call_recorder(lambda f: task))

    cli.invoke(projects.notify_pep_715, obj=config)
    assert config.task.calls == [
        pretend.call(send_pep_715_notices),
        pretend.call(send_pep_715_notices),
    ]
    assert task.get_request.calls == [pretend.call()]
    assert task.run.calls == [pretend.call(request)]
