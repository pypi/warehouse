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

from sqlalchemy import Column, DateTime, ForeignKey, String, orm, sql
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declared_attr

from warehouse import db


class Event:
    tag = Column(String, nullable=False)
    time = Column(DateTime, nullable=False, server_default=sql.func.now())
    ip_address = Column(String, nullable=False)
    additional = Column(JSONB, nullable=True)


class HasEvents:
    @declared_attr
    def events(cls):  # noqa: N805
        cls.Event = type(
            "%sEvent" % cls.__name__,
            (Event, db.Model),
            dict(
                __tablename__="%s_events" % cls.__tablename__,
                source_id=Column(
                    UUID(as_uuid=True),
                    ForeignKey(
                        "%s.id" % cls.__tablename__,
                        deferrable=True,
                        initially="DEFERRED",
                    ),
                    nullable=False,
                ),
                source=orm.relationship(cls),
            ),
        )
        return orm.relationship(cls.Event, cascade="all, delete-orphan", lazy=True)

    def record_event(self, *, tag, ip_address, additional=None):
        session = orm.object_session(self)
        event = self.Event(
            source=self, tag=tag, ip_address=ip_address, additional=additional
        )
        session.add(event)
        session.flush()

        return event
