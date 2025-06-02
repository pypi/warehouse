# SPDX-License-Identifier: Apache-2.0

from sqlalchemy import FetchedValue
from sqlalchemy.orm import Mapped, mapped_column


class SitemapMixin:
    sitemap_bucket: Mapped[str] = mapped_column(
        server_default=FetchedValue(),
        server_onupdate=FetchedValue(),
        index=True,
    )
