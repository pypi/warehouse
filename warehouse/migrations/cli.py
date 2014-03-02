# Copyright 2013 Donald Stufft
#
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import alembic.config
import alembic.command


class AlembicCommand(object):

    def __call__(self, app, *args, **kwargs):
        cfg = self._create_alembic_config(app)
        return self.command.__func__(cfg, *args, **kwargs)

    def _create_alembic_config(self, app):
        alembic_cfg = alembic.config.Config()
        alembic_cfg.set_main_option(
            "script_location",
            "warehouse:migrations",
        )
        alembic_cfg.set_main_option("url", app.config.database.url)

        return alembic_cfg


class BranchesCommand(AlembicCommand):

    command = alembic.command.branches


class CurrentCommand(AlembicCommand):

    command = alembic.command.current

    def create_parser(self, parser):
        parser.add_argument(
            "--head-only",
            action="store_true",
            dest="head_only",
            help=("Only show current version and whether or not this is the "
                  "head revision."),
        )


class DowngradeCommand(AlembicCommand):

    command = alembic.command.downgrade

    def create_parser(self, parser):
        parser.add_argument(
            "revision",
            help="revision identifier",
        )


class HistoryCommand(AlembicCommand):

    command = alembic.command.history

    def create_parser(self, parser):
        parser.add_argument(
            "-r", "--rev-range",
            dest="rev_range",
            help="Specify a revision range; format is [start]:[end]",
        )


class RevisionCommand(AlembicCommand):

    command = alembic.command.revision

    def create_parser(self, parser):
        parser.add_argument(
            "-m", "--message",
            dest="message",
            help="Message string to use with 'revision'",
        )
        parser.add_argument(
            "-a", "--autogenerate",
            action="store_true",
            dest="autogenerate",
            help=("Populate revision script with candidate migration "
                  "operations, based on comparison of database to model."),
        )


class StampCommand(AlembicCommand):

    command = alembic.command.stamp

    def create_parser(self, parser):
        parser.add_argument("revision", help="revision identifier")


class UpgradeCommand(AlembicCommand):

    command = alembic.command.upgrade

    def create_parser(self, parser):
        parser.add_argument("revision", help="revision identifier")


__commands__ = {
    "branches": BranchesCommand(),
    "current": CurrentCommand(),
    "downgrade": DowngradeCommand(),
    "history": HistoryCommand(),
    "revision": RevisionCommand(),
    "stamp": StampCommand(),
    "upgrade": UpgradeCommand(),
}
