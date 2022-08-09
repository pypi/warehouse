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

from securesystemslib.exceptions import StorageError

from warehouse.cli.tuf import (
    add_all_indexes,
    add_all_packages,
    bump_bin_n_roles,
    bump_snapshot,
    init_delegations,
    init_repo,
    keypair,
)
from warehouse.tuf.tasks import (
    add_hashed_targets as _add_hashed_targets,
    bump_bin_n_roles as _bump_bin_n_roles,
    bump_snapshot as _bump_snapshot,
    init_dev_repository as _init_dev_repository,
    init_targets_delegation as _init_targets_delegation,
)


class TestCLITUF:
    def test_keypair(self, cli, monkeypatch):
        settings = {"tuf.root.secret": "test_password"}
        registry = pretend.stub(settings=settings)
        config = pretend.stub(registry=registry)

        generate_and_write_ed25519_keypair = pretend.call_recorder(
            lambda *a, **kw: None
        )

        monkeypatch.setattr(
            "warehouse.cli.tuf.generate_and_write_ed25519_keypair",
            generate_and_write_ed25519_keypair,
        )
        result = cli.invoke(
            keypair, ["--name", "root", "--path", "def/tufkeys/root.key"], obj=config
        )

        assert result.exit_code == 0

    def test_keypair_required_name(self, cli):
        result = cli.invoke(keypair)
        assert result.exit_code == 2
        assert "Missing option '--name'" in result.output

    def test_keypair_required_path(self, cli):
        result = cli.invoke(keypair, ["--name", "root"])
        assert result.exit_code == 2
        assert "Missing option '--path'" in result.output, result.output

    def test_init_repo(self, cli):

        request = pretend.stub()
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(init_repo, obj=config)

        assert result.exit_code == 0
        assert "Repository Initialization finished." in result.output
        assert config.task.calls == [
            pretend.call(_init_dev_repository),
            pretend.call(_init_dev_repository),
        ]
        assert task.get_request.calls == [pretend.call()]
        assert task.run.calls == [pretend.call(request)]

    def test_init_repo_raise_fileexistserror(self, cli):

        request = pretend.stub()
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.raiser(FileExistsError("TUF Error detail")),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(init_repo, obj=config)

        assert result.exit_code == 1
        assert "Error: TUF Error detail\n" == result.output
        assert config.task.calls == [
            pretend.call(_init_dev_repository),
            pretend.call(_init_dev_repository),
        ]
        assert task.get_request.calls == [pretend.call()]

    def test_bump_snapshot(self, cli):

        request = pretend.stub()
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(bump_snapshot, obj=config)

        assert result.exit_code == 0
        assert "Snapshot bump finished." in result.output
        assert config.task.calls == [
            pretend.call(_bump_snapshot),
            pretend.call(_bump_snapshot),
        ]
        assert task.get_request.calls == [pretend.call()]
        assert task.run.calls == [pretend.call(request)]

    def test_bump_bin_n_roles(self, cli):

        request = pretend.stub()
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(bump_bin_n_roles, obj=config)

        assert result.exit_code == 0
        assert "BIN-N roles (hash bins) bump finished." in result.output
        assert config.task.calls == [
            pretend.call(_bump_bin_n_roles),
            pretend.call(_bump_bin_n_roles),
        ]
        assert task.get_request.calls == [pretend.call()]
        assert task.run.calls == [pretend.call(request)]

    def test_init_delegations(self, cli):
        request = pretend.stub()
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(init_delegations, obj=config)

        assert result.exit_code == 0
        assert "BINS and BIN-N roles targets delegation finished." in result.output
        assert config.task.calls == [
            pretend.call(_init_targets_delegation),
            pretend.call(_init_targets_delegation),
        ]
        assert task.get_request.calls == [pretend.call()]
        assert task.run.calls == [pretend.call(request)]

    def test_init_delegations_raise_fileexistserror(self, cli):
        request = pretend.stub()
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.raiser(FileExistsError("SSLIB Error detail")),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(init_delegations, obj=config)

        assert result.exit_code == 1
        assert "Error: SSLIB Error detail\n" == result.output
        assert config.task.calls == [
            pretend.call(_init_targets_delegation),
            pretend.call(_init_targets_delegation),
        ]
        assert task.get_request.calls == [pretend.call()]

    def test_init_delegations_raise_storageerror(self, cli):
        request = pretend.stub()
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.raiser(StorageError("TUF Error detail")),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(init_delegations, obj=config)

        assert result.exit_code == 1
        assert "Error: TUF Error detail\n" == result.output
        assert config.task.calls == [
            pretend.call(_init_targets_delegation),
            pretend.call(_init_targets_delegation),
        ]
        assert task.get_request.calls == [pretend.call()]

    def test_add_all_packages(self, cli, monkeypatch):

        fake_files = [
            pretend.stub(
                blake2_256_digest="01101234567890abcdef",
                size=192,
                path="00/11/0123456789abcdf",
            )
        ]
        all = pretend.stub(all=lambda: fake_files)
        session = pretend.stub(query=pretend.call_recorder(lambda *a, **kw: all))
        session_cls = pretend.call_recorder(lambda bind: session)
        monkeypatch.setattr("warehouse.db.Session", session_cls)
        monkeypatch.setattr("warehouse.packaging.models.File", lambda: None)

        settings = {"sqlalchemy.engine": "fake_engine"}
        request = pretend.stub(registry=settings)
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(add_all_packages, obj=config)

        assert result.exit_code == 0
        assert config.task.calls == [
            pretend.call(_add_hashed_targets),
            pretend.call(_add_hashed_targets),
        ]
        assert task.get_request.calls == [pretend.call()]

    def test_add_all_indexes(self, cli, monkeypatch):

        fake_projects = [
            pretend.stub(
                normalized_name="fake_project_name",
            )
        ]
        all = pretend.stub(all=lambda: fake_projects)
        session = pretend.stub(query=pretend.call_recorder(lambda *a, **kw: all))
        session_cls = pretend.call_recorder(lambda bind: session)
        monkeypatch.setattr("warehouse.db.Session", session_cls)
        monkeypatch.setattr("warehouse.packaging.models.Project", lambda: None)

        settings = {"sqlalchemy.engine": "fake_engine"}
        request = pretend.stub(registry=settings)
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        simple_detail = {"content_hash": "fake_hash", "length": 199}
        fake_render_simple_detail = pretend.call_recorder(
            lambda *a, **kw: simple_detail
        )
        monkeypatch.setattr(
            "warehouse.cli.tuf.render_simple_detail", fake_render_simple_detail
        )

        result = cli.invoke(add_all_indexes, obj=config)

        assert result.exit_code == 0
        assert config.task.calls == [
            pretend.call(_add_hashed_targets),
            pretend.call(_add_hashed_targets),
        ]
        assert task.get_request.calls == [pretend.call()]

    def test_add_all_indexes_content_hash_none(self, cli, monkeypatch):

        fake_projects = [
            pretend.stub(
                normalized_name="fake_project_name",
            )
        ]
        all = pretend.stub(all=lambda: fake_projects)
        session = pretend.stub(query=pretend.call_recorder(lambda *a, **kw: all))
        session_cls = pretend.call_recorder(lambda bind: session)
        monkeypatch.setattr("warehouse.db.Session", session_cls)
        monkeypatch.setattr("warehouse.packaging.models.Project", lambda: None)

        settings = {"sqlalchemy.engine": "fake_engine"}
        request = pretend.stub(registry=settings)
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        simple_detail = {"content_hash": None, "length": 199}
        fake_render_simple_detail = pretend.call_recorder(
            lambda *a, **kw: simple_detail
        )
        monkeypatch.setattr(
            "warehouse.cli.tuf.render_simple_detail", fake_render_simple_detail
        )

        result = cli.invoke(add_all_indexes, obj=config)

        assert result.exit_code == 1
        assert config.task.calls == [
            pretend.call(_add_hashed_targets),
        ]
        assert task.get_request.calls == [pretend.call()]

    def test_add_all_indexes_oserrors(self, cli, monkeypatch):

        fake_projects = [
            pretend.stub(
                normalized_name="fake_project_name",
            )
        ]
        all = pretend.stub(all=lambda: fake_projects)
        session = pretend.stub(query=pretend.call_recorder(lambda *a, **kw: all))
        session_cls = pretend.call_recorder(lambda bind: session)
        monkeypatch.setattr("warehouse.db.Session", session_cls)
        monkeypatch.setattr("warehouse.packaging.models.Project", lambda: None)

        settings = {"sqlalchemy.engine": "fake_engine"}
        request = pretend.stub(registry=settings)
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        fake_render_simple_detail = pretend.raiser(OSError)
        monkeypatch.setattr(
            "warehouse.cli.tuf.render_simple_detail", fake_render_simple_detail
        )

        result = cli.invoke(add_all_indexes, obj=config)

        assert result.exit_code == 1
        assert config.task.calls == [
            pretend.call(_add_hashed_targets),
        ]
        assert task.get_request.calls == [pretend.call()]
