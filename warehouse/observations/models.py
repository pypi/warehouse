# SPDX-License-Identifier: Apache-2.0

"""Observations and associated models."""
from __future__ import annotations

import enum
import typing

from uuid import UUID

from sqlalchemy import ForeignKey, String, sql
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.ext.declarative import AbstractConcreteBase
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from warehouse import db
from warehouse.utils.db.types import datetime_now

if typing.TYPE_CHECKING:
    from pyramid.request import Request

    from warehouse.accounts.models import User


class ObserverAssociation(db.Model):
    """Associate an Observer with a given parent."""

    __tablename__ = "observer_association"

    discriminator: Mapped[str] = mapped_column(comment="The type of the parent")
    observer: Mapped[Observer] = relationship(
        back_populates="_association", uselist=False
    )

    __mapper_args__ = {"polymorphic_on": discriminator}


class Observer(db.Model):
    __tablename__ = "observers"

    created: Mapped[datetime_now]

    _association_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(ObserverAssociation.id)
    )
    _association: Mapped[ObserverAssociation] = relationship(
        back_populates="observer", uselist=False
    )

    observations: Mapped[list[Observation]] = relationship()
    parent: AssociationProxy = association_proxy("_association", "parent")


class HasObservers:
    """A mixin for models that can have observers."""

    @declared_attr
    def observer_association_id(cls):  # noqa: N805
        return mapped_column(
            PG_UUID, ForeignKey(f"{ObserverAssociation.__tablename__}.id")
        )

    @declared_attr
    def observer_association(cls):  # noqa: N805
        name = cls.__name__
        discriminator = name.lower()

        assoc_cls = type(
            f"{name}ObserverAssociation",
            (ObserverAssociation,),
            dict(
                __tablename__=None,
                __mapper_args__={"polymorphic_identity": discriminator},
                parent=relationship(
                    name,
                    back_populates="observer_association",
                    uselist=False,
                ),
            ),
        )

        cls.observer = association_proxy(
            "observer_association",
            "observer",
            creator=lambda o: assoc_cls(observer=o),
        )
        return relationship(assoc_cls)


class ObservationKind(enum.Enum):
    """
    The kinds of observations we can make. Format:

    key_used_in_python = ("key_used_in_postgres", "Human Readable Name")

    Explicitly not a ForeignKey to a table, since we want to be able to add new
    kinds of observations without having to update the database schema.
    """

    # Projects
    IsDependencyConfusion = ("is_dependency_confusion", "Is Dependency Confusion")
    IsMalware = ("is_malware", "Is Malware")
    IsSpam = ("is_spam", "Is Spam")
    SomethingElse = ("something_else", "Something Else")

    # Accounts
    AccountAbuse = ("account_abuse", "Account Abuse")
    AccountRecovery = (
        "account_recovery",
        "Account Recovery",
    )
    EmailUnverified = ("email_unverified", "Email Unverified")

    # Organization Applications
    InformationRequest = ("information_request", "Information Request")


# A reverse-lookup map by the string value stored in the database
OBSERVATION_KIND_MAP = {kind.value[0]: kind for kind in ObservationKind}


class Observation(AbstractConcreteBase, db.Model):
    """
    Observations are user-driven additions to models.
    They may be used to add information to a model in a many-to-one relationship.

    The pattern followed is similar to `Event`/`HasEvents` in `warehouse.events.models`,
    based on `table_per_related` from
    https://docs.sqlalchemy.org/en/20/_modules/examples/generic_associations/table_per_related.html
    with the addition of using `AbstractConcreteBase` to allow for a cross-table
    relationship. Read more:
    https://docs.sqlalchemy.org/en/20/orm/inheritance.html#abstract-concrete-base
    """

    __mapper_args__ = {
        "polymorphic_identity": "observation",
    }

    created: Mapped[datetime_now] = mapped_column(
        comment="The time the observation was created"
    )
    kind: Mapped[str] = mapped_column(comment="The kind of observation")
    summary: Mapped[str] = mapped_column(comment="A short summary of the observation")
    payload: Mapped[dict] = mapped_column(
        JSONB, comment="The observation payload we received"
    )
    additional: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        comment="Additional data for the observation",
        server_default=sql.text("'{}'"),
    )
    actions: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        comment="Actions taken based on the observation",
        server_default=sql.text("'{}'"),
    )

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.kind}>"

    @property
    def kind_display(self) -> str:
        """
        Return the human-readable name of the observation kind.
        """
        kind_map = {k.value[0]: k.value[1] for k in ObservationKind}
        return kind_map[self.kind]


class HasObservations:
    """
    A mixin for models that can have Observations.
    Since Observations require a User to link to as the creator,
    any code using `record_observation()` will need to pass a
    `request` object that has a `user` attribute.
    For Views, when using `@view_config(..., uses_session=True)`,

    Usage:
        some_model.record_observation(...)
        some_model.observations  # a list of Observation objects
    """

    Observation: typing.ClassVar[type]

    @declared_attr
    def observations(cls):  # noqa: N805
        cls.Observation = type(
            f"{cls.__name__}Observation",
            (Observation, db.Model),
            dict(
                __tablename__=f"{cls.__name__.lower()}_observations",
                __mapper_args__={
                    "polymorphic_identity": cls.__name__.lower(),
                    "concrete": True,
                },
                related_id=mapped_column(
                    PG_UUID,
                    ForeignKey(f"{cls.__tablename__}.id"),
                    comment="The ID of the related model",
                    nullable=True,
                    index=True,
                ),
                related=relationship(cls, back_populates="observations"),
                related_name=mapped_column(
                    String,
                    comment="The name of the related model",
                    nullable=False,
                ),
                observer_id=mapped_column(
                    PG_UUID,
                    ForeignKey("observers.id"),
                    comment="ID of the Observer who created the Observation",
                    nullable=False,
                ),
                observer=relationship(Observer),
            ),
        )
        return relationship(cls.Observation)

    def record_observation(
        self,
        *,
        request: Request,
        kind: ObservationKind,
        actor: User,  # TODO: Expand type as we add more HasObserver models
        summary: str,
        payload: dict,
    ):
        """
        Record an observation on the related model.
        """
        if actor.observer is None:
            actor.observer = Observer()

        observation = self.Observation(
            kind=kind.value[0],
            observer=actor.observer,
            payload=payload,
            related=self,
            related_name=repr(self),
            summary=summary,
        )

        request.db.add(observation)

        return observation
