# SPDX-License-Identifier: Apache-2.0
from dataclasses import field

import pyramid_components as pc


@pc.register("admin.stat_card")
class StatCard(pc.Component):
    """An AdminLTE "small-box" dashboard stat card.

    ``color`` is the box's modifier class string (e.g. "bg-gradient-info",
    optionally with extra classes like "bg-gradient-teal utilization-card").
    URLs and any request-derived values are computed at the call site and
    passed in as plain strings.
    """

    template = "warehouse.admin:components/stat_card/stat_card.html"

    class Props:
        color: str
        value: str
        icon: str = "fa-box"
        sublines: list[str] = field(default_factory=list)
        description: str | None = None
        footer_url: str | None = None
        footer_text: str = "View All"
        tooltip: str | None = None
