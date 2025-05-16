# SPDX-License-Identifier: Apache-2.0

from factory.alchemy import SQLAlchemyModelFactory

from . import Session


class WarehouseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session = Session

    @classmethod
    def _setup_next_sequence(cls, *args, **kwargs):
        return 0

    @classmethod
    def _create(cls, *args, **kwargs):
        r = super()._create(*args, **kwargs)
        session = cls._meta.sqlalchemy_session
        session.flush()
        session.expire_all()
        return r
