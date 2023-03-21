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

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, orm, sql
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.declarative import AbstractConcreteBase
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import declared_attr

from warehouse import db
from warehouse.ip_addresses.models import IpAddress


class Event(AbstractConcreteBase):
    tag = Column(String, nullable=False)
    time = Column(DateTime, nullable=False, server_default=sql.func.now())
    ip_address_string = Column(String, nullable=True)
    additional = Column(JSONB, nullable=True)

    @declared_attr
    def ip_address_id(cls):  # noqa: N805
        return Column(
            UUID(as_uuid=True),
            ForeignKey("ip_addresses.id", onupdate="CASCADE", ondelete="CASCADE"),
            nullable=True,
        )

    @declared_attr
    def __tablename__(cls):  # noqa: N805
        return "_".join([cls.__name__.removesuffix("Event").lower(), "events"])

    @declared_attr
    def __table_args__(cls):  # noqa: N805
        return (Index(f"ix_{ cls.__tablename__ }_source_id", "source_id"),)

    @declared_attr
    def __mapper_args__(cls):  # noqa: N805
        return (
            {"polymorphic_identity": cls.__name__, "concrete": True}
            if cls.__name__ != "Event"
            else {}
        )

    @declared_attr
    def source_id(cls):  # noqa: N805
        return Column(
            UUID(as_uuid=True),
            ForeignKey(
                "%s.id" % cls._parent_class.__tablename__,
                deferrable=True,
                initially="DEFERRED",
                ondelete="CASCADE",
            ),
            nullable=False,
        )

    @declared_attr
    def source(cls):  # noqa: N805
        return orm.relationship(cls._parent_class, back_populates="events")

    @declared_attr
    def ip_address_obj(cls):  # noqa: N805
        return orm.relationship(IpAddress)

    @hybrid_property
    def ip_address(cls):  # noqa: N805
        if cls.ip_address_obj is not None:
            return cls.ip_address_obj
        return cls.ip_address_string

    # ref: https://github.com/python/mypy/issues/11008
    @ip_address.setter  # type: ignore
    def ip_address(cls, value):  # noqa: N805
        session = orm.object_session(cls)

        cls.ip_address_string = value
        try:
            _ip_address = (
                session.query(IpAddress).filter(IpAddress.ip_address == value).one()
            )
        except NoResultFound:
            _ip_address = IpAddress(ip_address=value)
            session.add(_ip_address)
        cls.ip_address_obj = _ip_address

    def __init_subclass__(cls, /, parent_class, **kwargs):
        cls._parent_class = parent_class
        return cls


class HasEvents:
    def __init_subclass__(cls, /, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.Event = type(
            f"{cls.__name__}Event", (Event, db.Model), dict(), parent_class=cls
        )
        return cls

    @declared_attr
    def events(cls):  # noqa: N805
        return orm.relationship(
            cls.Event,
            cascade="all, delete-orphan",
            passive_deletes=True,
            lazy="dynamic",
            back_populates="source",
        )

    def record_event(self, *, tag, ip_address, additional=None):
        session = orm.object_session(self)
        event = self.Event(
            source=self,
            tag=tag,
            ip_address=ip_address,
            additional=additional,
        )
        session.add(event)

        return event
