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

from warehouse.cli.search import reindex
from warehouse.search.tasks import reindex as _reindex


class TestCLISearch:

    def test_reindex(self, cli):
        request = pretend.stub()
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(
            task=pretend.call_recorder(lambda *a, **kw: task)
        )

        result = cli.invoke(reindex, obj=config)

        assert result.exit_code == 0
        assert config.task.calls == [
            pretend.call(_reindex),
            pretend.call(_reindex),
        ]
        assert task.get_request.calls == [pretend.call()]
        assert task.run.calls == [pretend.call(request)]
