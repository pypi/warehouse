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
import hashlib

import pretend

from warehouse import db
from warehouse.cli import hashing

from ...common.db.packaging import JournalEntry, JournalEntryFactory


def remote_addr_salty_hash(remote_addr, salt):
    return hashlib.sha256(f"{remote_addr}{salt}".encode()).hexdigest()


class TestHashingJournalEntry:
    def test_no_records_to_hash(self, cli, db_request, monkeypatch):
        engine = pretend.stub()
        config = pretend.stub(registry={"sqlalchemy.engine": engine})
        session_cls = pretend.call_recorder(lambda bind: db_request.db)
        monkeypatch.setattr(db, "Session", session_cls)

        assert db_request.db.query(JournalEntry).count() == 0

        args = ["--salt", "test"]

        result = cli.invoke(hashing.journal_entry, args, obj=config)

        assert result.exit_code == 0
        assert result.output.strip() == "No rows to hash. Done!"

    def tests_hashes_records(self, cli, db_request, remote_addr, monkeypatch):
        engine = pretend.stub()
        config = pretend.stub(registry={"sqlalchemy.engine": engine})
        session_cls = pretend.call_recorder(lambda bind: db_request.db)
        monkeypatch.setattr(db, "Session", session_cls)

        # create some JournalEntry records with unhashed ip addresses
        JournalEntryFactory.create_batch(3, submitted_from=remote_addr)
        assert db_request.db.query(JournalEntry).count() == 3

        salt = "NaCl"
        salted_hash = remote_addr_salty_hash(remote_addr, salt)

        args = [
            "--salt",
            salt,
            "--batch-size",
            "2",
        ]

        result = cli.invoke(hashing.journal_entry, args, obj=config)

        assert result.exit_code == 0
        assert result.output.strip() == "Hashing 2 rows...\nHashed 2 rows"
        # check that two of the ip addresses have been hashed
        assert (
            db_request.db.query(JournalEntry)
            .filter_by(submitted_from=remote_addr)
            .one()
        )
        assert (
            db_request.db.query(JournalEntry)
            .filter_by(submitted_from=salted_hash)
            .count()
            == 2
        )

    def test_continue_until_done(self, cli, db_request, remote_addr, monkeypatch):
        engine = pretend.stub()
        config = pretend.stub(registry={"sqlalchemy.engine": engine})
        session_cls = pretend.call_recorder(lambda bind: db_request.db)
        monkeypatch.setattr(db, "Session", session_cls)

        # create some JournalEntry records with unhashed ip addresses
        JournalEntryFactory.create_batch(3, submitted_from=remote_addr)

        salt = "NaCl"
        salted_hash = remote_addr_salty_hash(remote_addr, salt)

        args = [
            "--salt",
            salt,
            "--batch-size",
            "1",
            "--sleep-time",
            "0",
            "--continue-until-done",
        ]

        result = cli.invoke(hashing.journal_entry, args, obj=config)

        assert result.exit_code == 0
        # check that all the ip addresses have been hashed
        assert (
            db_request.db.query(JournalEntry)
            .filter_by(submitted_from=salted_hash)
            .count()
            == 3
        )
        assert (
            db_request.db.query(JournalEntry)
            .filter_by(submitted_from=remote_addr)
            .count()
            == 0
        )
