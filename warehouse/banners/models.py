# SPDX-License-Identifier: Apache-2.0

from datetime import date

from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.utils.attrs import make_repr
from warehouse.utils.db.types import bool_false


class Banner(db.Model):
    __tablename__ = "banners"
    __repr__ = make_repr("text")
    DEFAULT_FA_ICON = "fa-comment-alt"
    DEFAULT_BTN_LABEL = "See more"

    # internal name
    name: Mapped[str]

    # banner display configuration
    text: Mapped[str]
    link_url: Mapped[str]
    link_label: Mapped[str] = mapped_column(default=DEFAULT_BTN_LABEL)
    fa_icon: Mapped[str] = mapped_column(default=DEFAULT_FA_ICON)
    dismissable: Mapped[bool_false]

    # visibility control
    # TODO: Migrate to `warehouse.utils.db.types.bool_false` - triggers migration
    active: Mapped[bool] = mapped_column(default=False)
    end: Mapped[date]

    @property
    def is_live(self):
        # date.today is using the server timezone which is UTC
        return self.active and date.today() <= self.end
