# SPDX-License-Identifier: Apache-2.0

from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.utils import readme
from warehouse.utils.attrs import make_repr


class Sponsor(db.Model):
    __tablename__ = "sponsors"
    __repr__ = make_repr("name")

    name: Mapped[str]
    service: Mapped[str | None]
    activity_markdown: Mapped[str | None]

    link_url: Mapped[str]
    color_logo_url: Mapped[str]
    white_logo_url: Mapped[str | None]

    # control flags
    # TODO: These cannot use `bool_false` type, as `default=False` is performed
    #  locally prior to sending the value to the database.
    #  Changing incurs a migration, which we should do as a later refactor.
    is_active: Mapped[bool] = mapped_column(default=False)
    footer: Mapped[bool] = mapped_column(default=False)
    psf_sponsor: Mapped[bool] = mapped_column(default=False)
    infra_sponsor: Mapped[bool] = mapped_column(default=False)
    one_time: Mapped[bool] = mapped_column(default=False)
    sidebar: Mapped[bool] = mapped_column(default=False)

    # pythondotorg integration
    origin: Mapped[str | None] = mapped_column(default="manual")
    level_name: Mapped[str | None]
    level_order: Mapped[int | None] = mapped_column(default=0)
    slug: Mapped[str | None]

    @property
    def color_logo_img(self):
        return f'<img src="{self.color_logo_url}" alt="" loading="lazy">'

    @property
    def white_logo_img(self):
        if not self.white_logo_url:
            return ""
        return (
            '<img class="sponsors__image" '
            + f'src="{self.white_logo_url}" alt="" loading="lazy">'
        )

    @property
    def activity(self):
        """
        Render raw activity markdown as HTML
        """
        if not self.activity_markdown:
            return ""
        return readme.render(self.activity_markdown, "text/markdown")
