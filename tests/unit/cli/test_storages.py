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

from warehouse.cli.storages import reconcile
from warehouse.packaging.tasks import (
    reconcile_file_storages as _reconcile_file_storages,
)


class TestCLIStorages:
    def test_reindex(self, cli):
        request = pretend.stub(
            registry=pretend.stub(settings={"reconcile_file_storages.batch_size": 1000})
        )
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(reconcile, obj=config)

        assert result.exit_code == 0
        assert config.task.calls == [
            pretend.call(_reconcile_file_storages),
            pretend.call(_reconcile_file_storages),
        ]
        assert task.get_request.calls == [pretend.call()]
        assert task.run.calls == [pretend.call(request)]
