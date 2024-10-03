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

        post = call_recorder(lambda *a: self.task_id)
        monkeypatch.setattr(tuf.tasks, "post_artifacts", post)

        wait = call_recorder(lambda *a: None)
        monkeypatch.setattr(tuf.tasks, "wait_for_success", wait)

        tuf.tasks.update_metadata(db_request, project_id)
        assert one.calls == [call()]
        assert render.calls == [call(project, db_request, store=True)]
        assert post.calls == [
            call(
                rstuf_url,
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
        assert wait.calls == [call(rstuf_url, self.task_id)]

    def test_update_metadata_no_rstuf_api_url(self, db_request):
        project_id = "id"
        project_name = "name"

        project = stub(normalized_name=project_name)

        one = call_recorder(lambda: project)
        db_request.db.query = lambda a: stub(filter=lambda a: stub(one=one))

        # Test early return, if no RSTUF API URL configured
        db_request.registry.settings = {"rstuf.api_url": None}
        tuf.tasks.update_metadata(db_request, project_id)

        assert not one.calls
