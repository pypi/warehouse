# SPDX-License-Identifier: Apache-2.0
import pyramid_components as pc


@pc.register("admin.info_box")
class InfoBox(pc.Component):
    """An AdminLTE "info-box": a colored icon tile beside a label and number.

    ``number`` is the already-formatted value (e.g. "42" or "37%"); compute any
    conditional or request-derived value at the call site and pass it in as a
    plain string. ``subtext`` renders a small line under the number when given.
    """

    template = "warehouse.admin:components/info_box/info_box.html"

    class Props:
        icon_bg: str  # icon background class, e.g. "bg-info"
        icon: str  # Font Awesome icon class, e.g. "fa-bullhorn"
        text: str  # label, e.g. "Total Reports"
        number: str  # value, formatted at the call site
        subtext: str | None = None
