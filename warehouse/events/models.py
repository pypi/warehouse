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
from __future__ import annotations

import typing

from dataclasses import dataclass

from linehaul.ua import parser as linehaul_user_agent_parser
from sqlalchemy import Column, DateTime, ForeignKey, Index, String, orm, sql
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.declarative import AbstractConcreteBase
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import declared_attr
from ua_parser import user_agent_parser

from warehouse import db
from warehouse.ip_addresses.models import IpAddress

if typing.TYPE_CHECKING:
    from pyramid.request import Request


@dataclass
class GeoIPInfo:
    """
    Optional values passed in from upstream CDN
    https://github.com/pypi/infra/blob/3e57592ba91205cb5d10c588d529767b101753cd/terraform/warehouse/vcl/main.vcl#L181-L191
    """

    city: str | None = None
    continent_code: str | None = None
    country_code3: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    region: str | None = None

    @property
    def _city(self) -> str:
        return self.city.title() if self.city else ""

    @property
    def _region(self) -> str:
        return self.region.upper() if self.region else ""

    @property
    def _country_code(self) -> str:
        return self.country_code.upper() if self.country_code else ""

    def display(self) -> str:
        """
        Construct a reasonable location, depending on optional values
        """
        if self.city and self.region and self.country_code:
            return f"{self._city}, {self._region}, {self._country_code}"
        elif self.city and self.region:
            return f"{self._city}, {self._region}"
        elif self.city and self.country_code:
            return f"{self._city}, {self._country_code}"
        elif self.region:
            return f"{self._region}, {self._country_code}"
        elif self.country_name:
            return self.country_name
        return ""


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

    @property
    def location_info(cls) -> str:  # noqa: N805
        """
        Determine "best" location info to display.

        Dig into `.additional` for `geoip_info` and return that if it exists.
        It was stored at the time opf the event, and may change in the related
        `IpAddress` object over time.
        Otherwise, return the `ip_address_obj` and let its repr decide.
        """
        if cls.additional is not None and "geoip_info" in cls.additional:
            g = GeoIPInfo(**cls.additional["geoip_info"])
            if g.display():
                return g.display()

        return cls.ip_address_obj

    def __init_subclass__(cls, /, parent_class, **kwargs):
        cls._parent_class = parent_class
        return cls


class HasEvents:
    Event: typing.ClassVar[type]

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

    def record_event(self, *, tag, ip_address, request: Request, additional=None):
        """Records an Event record on the associated model."""
        session = orm.object_session(self)

        # Get-or-create a new IpAddress object
        ip_address_obj = request.ip_address
        # Add `request.ip_address.geoip_info` data to `Event.additional`
        if ip_address_obj.geoip_info is not None:
            additional = additional or {}
            additional["geoip_info"] = ip_address_obj.geoip_info

        if user_agent := request.headers.get("User-Agent"):
            try:
                parsed_user_agent = linehaul_user_agent_parser.parse(user_agent)
                if (
                    parsed_user_agent is not None
                    and parsed_user_agent.installer is not None
                    and parsed_user_agent.installer.name == "Browser"
                ):
                    parsed_user_agent = user_agent_parser.Parse(user_agent)
                    additional = additional or {}
                    additional["user_agent_info"] = {
                        "installer": "Browser",
                        "device": parsed_user_agent["device"]["family"],
                        "os": parsed_user_agent["os"]["family"],
                        "user_agent": parsed_user_agent["user_agent"]["family"],
                    }
                else:
                    additional = additional or {}
                    additional["user_agent_info"] = {
                        "installer": parsed_user_agent.installer.name
                        if parsed_user_agent and parsed_user_agent.installer
                        else None,
                        "implementation": parsed_user_agent.implementation.name
                        if parsed_user_agent and parsed_user_agent.implementation
                        else None,
                        "system": parsed_user_agent.system.name
                        if parsed_user_agent and parsed_user_agent.system
                        else None,
                    }
            except linehaul_user_agent_parser.UnknownUserAgentError:
                pass

        event = self.Event(
            source=self,
            tag=tag,
            ip_address_obj=ip_address_obj,
            additional=additional,
        )

        session.add(event)

        return event
