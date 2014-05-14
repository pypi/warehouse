import datetime
import random

import factory

from factory import base
from factory.fuzzy import (
    BaseFuzzyAttribute, FuzzyText, FuzzyNaiveDateTime, FuzzyInteger,
    FuzzyChoice,
)

from warehouse.packaging.tables import packages, releases, release_files
from warehouse.utils import normalize_project_name


def table_shim(table):
    class FakeTable(dict):
        __table__ = table

    return FakeTable


class FuzzyVersion(BaseFuzzyAttribute):

    def __init__(self, length=3):
        self.length = length

    def fuzz(self):
        return ".".join(
            str(random.randint(0, 100)) for _ in range(self.length)
        )


class WarehouseFactory(base.Factory):

    @classmethod
    def _create(cls, target_class, *args, **kwargs):
        engine = kwargs.pop("engine")
        obj = target_class(*args, **kwargs)
        engine.execute(target_class.__table__.insert().values(**obj))
        return obj


class ProjectFactory(WarehouseFactory):
    FACTORY_FOR = table_shim(packages)

    name = FuzzyText()
    normalized_name = factory.LazyAttribute(
        lambda obj: normalize_project_name(obj.name)
    )


class ReleaseFactory(WarehouseFactory):
    FACTORY_FOR = table_shim(releases)

    version = FuzzyVersion()
    summary = FuzzyText(length=75)
    created = FuzzyNaiveDateTime(
        datetime.datetime.now() - datetime.timedelta(days=5),
    )


class ReleaseFileFactory(WarehouseFactory):
    FACTORY_FOR = table_shim(release_files)
    FACTORY_HIDDEN_ARGS = ["EXTS"]

    EXTS = {
        "sdist": ".tar.gz",
    }

    packagetype = FuzzyChoice(["sdist"])
    filename = factory.LazyAttribute(
        lambda obj: "{}-{}{}".format(
            obj.name,
            obj.version,
            obj.EXTS[obj.packagetype],
        )
    )
    downloads = FuzzyInteger(10000)
