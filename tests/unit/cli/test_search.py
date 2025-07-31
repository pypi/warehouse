# SPDX-License-Identifier: Apache-2.0

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
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(reindex, obj=config)

        assert result.exit_code == 0
        assert config.task.calls == [pretend.call(_reindex), pretend.call(_reindex)]
        assert task.get_request.calls == [pretend.call()]
        assert task.run.calls == [pretend.call(request)]
