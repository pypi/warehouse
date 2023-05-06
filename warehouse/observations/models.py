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
from sqlalchemy.ext.declarative import AbstractConcreteBase
from sqlalchemy.orm import declared_attr

from warehouse import db


class Observation(AbstractConcreteBase):
    kind = Column(String, nullable=False)
    time = Column(DateTime, nullable=False, server_default=sql.func.now())
    additional = Column(JSONB, nullable=True)

    @declared_attr
    def __tablename__(cls):  # noqa: N805
        return "_".join(
            [cls.__name__.removesuffix("Observation").lower(), "observations"]
        )

    @declared_attr
    def __table_args__(cls):  # noqa: N805
        return (Index(f"ix_{ cls.__tablename__ }_subject_id", "subject_id"),)

    @declared_attr
    def __mapper_args__(cls):  # noqa: N805
        return (
            {"polymorphic_identity": cls.__name__, "concrete": True}
            if cls.__name__ != "Observation"
            else {}
        )

    @declared_attr
    def subject_id(cls):  # noqa: N805
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
    def subject(cls):  # noqa: N805
        return orm.relationship(cls._parent_class, back_populates="observations")

    def __init_subclass__(cls, /, parent_class, **kwargs):
        cls._parent_class = parent_class
        return cls


class HasObservations:
    def __init_subclass__(cls, /, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.Observation = type(
            f"{cls.__name__}Observation",
            (Observation, db.Model),
            dict(),
            parent_class=cls,
        )
        return cls

    @declared_attr
    def observations(cls):  # noqa: N805
        return orm.relationship(
            cls.Observation,
            cascade="all, delete-orphan",
            passive_deletes=True,
            lazy="dynamic",
            back_populates="subject",
        )

    def record_observation(self, *, kind, additional=None):
        session = orm.object_session(self)
        observation = self.Observation(
            subject=self,
            kind=kind,
            additional=additional,
        )
        session.add(observation)

        return observation
