# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from dataclasses import dataclass
from uuid import UUID

from linehaul.ua import parser as linehaul_user_agent_parser
from sqlalchemy import ForeignKey, Index, orm
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from ua_parser import user_agent_parser

from warehouse import db
from warehouse.ip_addresses.models import IpAddress
from warehouse.utils.db.types import datetime_now

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
    latitude: float | None = None
    longitude: float | None = None

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


@dataclass
class UserAgentInfo:
    installer: str | None = None
    device: str | None = None
    os: str | None = None
    user_agent: str | None = None
    implementation: str | None = None
    system: str | None = None

    def display(self) -> str:
        """
        Construct a resonable user-agent description,
        depending on optional values
        """

        if self.installer == "Browser":
            if (
                self.device != "Other"
                and self.os != "Other"
                and self.user_agent != "Other"
            ):
                return f"{self.user_agent} ({self.os} on {self.device})"
            elif self.device != "Other" and self.user_agent != "Other":
                return f"{self.user_agent} ({self.device})"
            elif self.os != "Other" and self.user_agent != "Other":
                return f"{self.user_agent} ({self.os})"
            elif self.user_agent != "Other":
                return f"{self.user_agent}"
            else:
                return "Unknown Browser"
        elif self.installer is not None:
            if self.implementation and self.system:
                return f"{self.installer} ({self.implementation} " f"on {self.system})"
            elif self.implementation:
                return f"{self.installer} ({self.implementation})"
            elif self.system:
                return f"{self.installer} ({self.system})"
            else:
                return self.installer
        else:
            return "Unknown User-Agent"


class Event:
    tag: Mapped[str]
    time: Mapped[datetime_now]
    additional: Mapped[dict | None] = mapped_column(JSONB)

    if typing.TYPE_CHECKING:
        # Attributes defined on concrete subclasses created by HasEvents.
        # Declared here for type checking when querying via polymorphic union.
        source_id: Mapped[UUID]
        source: HasEvents

    @declared_attr
    def ip_address_id(cls):  # noqa: N805
        return mapped_column(
            ForeignKey("ip_addresses.id", onupdate="CASCADE", ondelete="CASCADE"),
            nullable=True,
        )

    @declared_attr
    def ip_address(cls):  # noqa: N805
        return orm.relationship(IpAddress)

    @property
    def location_info(cls) -> str | IpAddress:  # noqa: N805
        """
        Determine "best" location info to display.

        Dig into `.additional` for `geoip_info` and return that if it exists.
        It was stored at the time of the event, and may change in the related
        `IpAddress` object over time.
        Otherwise, return the `ip_address` and let its repr decide.
        """
        if cls.additional is not None and "geoip_info" in cls.additional:
            g = GeoIPInfo(**cls.additional["geoip_info"])
            if g.display():
                return g.display()

        return cls.ip_address

    @property
    def user_agent_info(cls) -> str:  # noqa: N805
        """
        Display a summarized User-Agent if available

        Dig into `.additional` for `user_agent_info` and return that if it exists.
        """
        if cls.additional is not None and "user_agent_info" in cls.additional:
            return UserAgentInfo(**cls.additional["user_agent_info"]).display()

        return "No User-Agent"


class HasEvents:
    if typing.TYPE_CHECKING:
        # Dynamically created Event subclass; typed as Any because:
        # - `type[Event]` breaks instantiation
        # - Needs to support both `cls.Event(...)` and `cls.Event.column` access
        Event: typing.Any

    @declared_attr
    def events(cls: type[typing.Any]):  # noqa: N805
        # Returns AppenderQuery at runtime (`lazy="dynamic"`)
        # No return type annotation: `Mapped[]` implies `uselist=False`,
        # `typing.Any` triggers SQLAlchemy error
        cls.Event = type(
            f"{cls.__name__}Event",
            (Event, db.Model),
            dict(
                __tablename__=f"{cls.__name__.lower()}_events",
                __table_args__=(
                    Index(f"ix_{cls.__name__.lower()}_events_source_id", "source_id"),
                ),
                source_id=mapped_column(
                    ForeignKey(
                        f"{cls.__tablename__}.id",
                        deferrable=True,
                        initially="DEFERRED",
                        ondelete="CASCADE",
                    ),
                    nullable=False,
                ),
                source=orm.relationship(
                    cls,
                    back_populates="events",
                    order_by=f"desc({cls.__name__}Event.time)",
                ),
            ),
        )
        return orm.relationship(
            cls.Event,
            cascade="all, delete-orphan",
            passive_deletes=True,
            lazy="dynamic",
            back_populates="source",
            order_by=f"desc({cls.__name__}Event.time)",
        )

    def record_event(self, *, tag, request: Request, additional=None):
        """Records an Event record on the associated model."""

        # Get-or-create a new IpAddress object
        ip_address = request.ip_address
        # Add `request.ip_address.geoip_info` data to `Event.additional`
        if ip_address.geoip_info is not None:
            additional = additional or {}
            additional["geoip_info"] = ip_address.geoip_info

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
                        # See https://github.com/pypi/linehaul-cloud-function/issues/203
                        "device": parsed_user_agent["device"]["family"],  # noqa: E501
                        "os": parsed_user_agent["os"]["family"],
                        "user_agent": parsed_user_agent["user_agent"][
                            "family"
                        ],  # noqa: E501
                    }
                else:
                    additional = additional or {}
                    additional["user_agent_info"] = {
                        "installer": (
                            parsed_user_agent.installer.name
                            if parsed_user_agent and parsed_user_agent.installer
                            else None
                        ),
                        "implementation": (
                            parsed_user_agent.implementation.name
                            if parsed_user_agent and parsed_user_agent.implementation
                            else None
                        ),
                        "system": (
                            parsed_user_agent.system.name
                            if parsed_user_agent and parsed_user_agent.system
                            else None
                        ),
                    }
            except linehaul_user_agent_parser.UnknownUserAgentError:
                pass

        event = self.Event(
            source=self,
            tag=tag,
            ip_address=ip_address,
            additional=additional,
        )

        request.db.add(event)

        return event
