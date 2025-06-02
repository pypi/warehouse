# SPDX-License-Identifier: Apache-2.0

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.utils.attrs import make_repr


class Classifier(db.ModelBase):
    __tablename__ = "trove_classifiers"
    __tableargs__ = CheckConstraint(
        "classifier not ilike 'private ::%'",
        name="ck_disallow_private_top_level_classifier",
    )

    __repr__ = make_repr("classifier")

    id: Mapped[int] = mapped_column(primary_key=True)
    classifier: Mapped[str | None] = mapped_column(unique=True)
    ordering: Mapped[int | None]
