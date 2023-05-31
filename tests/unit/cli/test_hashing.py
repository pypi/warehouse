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

import factory
import pretend

from warehouse import db
from warehouse.accounts.models import User
from warehouse.cli import hashing

from ...common.db.accounts import UserEventFactory, UserFactory
from ...common.db.ip_addresses import IpAddress


class TestBackfillIpAddresses:
    def test_no_records_to_backfill(self, cli, db_request, monkeypatch):
        engine = pretend.stub()
        registry_dict = {}
        config = pretend.stub(
            registry=pretend.stub(
                __getitem__=registry_dict.__getitem__,
                __setitem__=registry_dict.__setitem__,
                settings={"warehouse.ip_salt": "NaCl"},
            )
        )
        config.registry["sqlalchemy.engine"] = engine
        session_cls = pretend.call_recorder(lambda bind: db_request.db)
        monkeypatch.setattr(db, "Session", session_cls)

        assert db_request.db.query(User.Event).count() == 0

        args = ["--event-type", "user"]
        result = cli.invoke(hashing.backfill_ipaddrs, args, obj=config)

        assert result.exit_code == 0
        assert result.output.strip() == "No rows to backfill. Done!"

    def test_backfill_with_no_ipaddr_obj(self, cli, db_session, monkeypatch):
        engine = pretend.stub()
        registry_dict = {}
        config = pretend.stub(
            registry=pretend.stub(
                __getitem__=registry_dict.__getitem__,
                __setitem__=registry_dict.__setitem__,
                settings={"warehouse.ip_salt": "NaCl"},
            )
        )
        config.registry["sqlalchemy.engine"] = engine
        session_cls = pretend.call_recorder(lambda bind: db_session)
        monkeypatch.setattr(db, "Session", session_cls)

        user = UserFactory.create()
        UserEventFactory.create_batch(
            3,
            source=user,
            tag="dummy:tag",
            ip_address_string=factory.Faker("ipv4"),
        )
        assert db_session.query(User.Event).count() == 3
        assert db_session.query(IpAddress).count() == 0

        args = ["--event-type", "user"]
        result = cli.invoke(hashing.backfill_ipaddrs, args, obj=config)

        assert result.exit_code == 0
        assert db_session.query(IpAddress).count() == 3

    def tests_backfills_records(self, cli, db_request, remote_addr, monkeypatch):
        engine = pretend.stub()
        registry_dict = {}
        config = pretend.stub(
            registry=pretend.stub(
                __getitem__=registry_dict.__getitem__,
                __setitem__=registry_dict.__setitem__,
                settings={"warehouse.ip_salt": "NaCl"},
            )
        )
        config.registry["sqlalchemy.engine"] = engine
        session_cls = pretend.call_recorder(lambda bind: db_request.db)
        monkeypatch.setattr(db, "Session", session_cls)

        user = UserFactory.create()
        UserEventFactory.create_batch(
            3,
            source=user,
            tag="dummy:tag",
            ip_address_string=remote_addr,
        )
        assert db_request.db.query(User.Event).count() == 3

        args = [
            "--event-type",
            "user",
            "--batch-size",
            "2",
        ]

        result = cli.invoke(hashing.backfill_ipaddrs, args, obj=config)

        assert result.exit_code == 0
        assert result.output.strip() == "Backfilling 2 rows...\nBackfilled 2 rows"
        # check that two of the ip addresses have been hashed
        assert (
            db_request.db.query(User.Event)
            .where(User.Event.ip_address_id.is_not(None))
            .count()
            == 2
        )
        # and that there's only a single unassociated ip address left
        assert (
            db_request.db.query(User.Event)
            .where(User.Event.ip_address_id.is_(None))
            .one()
        )

    def test_continue_until_done(self, cli, db_request, remote_addr, monkeypatch):
        engine = pretend.stub()
        registry_dict = {}
        config = pretend.stub(
            registry=pretend.stub(
                __getitem__=registry_dict.__getitem__,
                __setitem__=registry_dict.__setitem__,
                settings={"warehouse.ip_salt": "NaCl"},
            )
        )
        config.registry["sqlalchemy.engine"] = engine
        session_cls = pretend.call_recorder(lambda bind: db_request.db)
        monkeypatch.setattr(db, "Session", session_cls)

        user = UserFactory.create()
        UserEventFactory.create_batch(
            3,
            source=user,
            tag="dummy:tag",
            ip_address_string=remote_addr,
        )

        args = [
            "--event-type",
            "user",
            "--batch-size",
            "1",
            "--sleep-time",
            "0",
            "--continue-until-done",
        ]

        result = cli.invoke(hashing.backfill_ipaddrs, args, obj=config)

        assert result.exit_code == 0
        # check that all the ip addresses have been associated
        assert (
            db_request.db.query(User.Event)
            .where(User.Event.ip_address_id.is_not(None))
            .count()
            == 3
        )
        assert (
            db_request.db.query(User.Event)
            .where(User.Event.ip_address_id.is_(None))
            .count()
            == 0
        )
