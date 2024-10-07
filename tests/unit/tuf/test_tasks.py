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
from pretend import call, call_recorder, stub

from warehouse import tuf


class TestTUFTasks:
    task_id = "123456"

    def test_update_metadata(self, db_request, monkeypatch):
        project_id = "id"
        project_name = "name"

        project = stub(normalized_name=project_name)

        one = call_recorder(lambda: project)
        db_request.db.query = lambda a: stub(filter=lambda a: stub(one=one))

        rstuf_url = "url"
        index_digest = "digest"
        index_size = 42

        db_request.registry.settings = {"rstuf.api_url": rstuf_url}

        render = call_recorder(lambda *a, **kw: (index_digest, None, index_size))
        tuf.tasks.render_simple_detail = render

        rstuf = tuf.services.RSTUFService.create_service(db_request)
        rstuf.post_artifacts = call_recorder(lambda *a: self.task_id)
        rstuf.wait_for_success = call_recorder(lambda *a: None)
        db_request.find_service = call_recorder(lambda *a, **kw: rstuf)

        tuf.tasks.update_metadata(db_request, project_id)
        assert one.calls == [call()]
        assert render.calls == [call(project, db_request, store=True)]
        assert rstuf.post_artifacts.calls == [
            call(
                {
                    "targets": [
                        {
                            "path": project_name,
                            "info": {
                                "length": index_size,
                                "hashes": {"blake2b-256": index_digest},
                            },
                        }
                    ]
                },
            )
        ]
        assert rstuf.wait_for_success.calls == [call(self.task_id)]
