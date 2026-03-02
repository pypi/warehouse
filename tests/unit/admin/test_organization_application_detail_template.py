# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import warehouse


def test_request_more_info_modal_has_two_triggers():
    template_path = (
        Path(warehouse.__path__[0])
        / "admin"
        / "templates"
        / "admin"
        / "organization_applications"
        / "detail.html"
    )
    content = template_path.read_text(encoding="utf-8")

    # Top "Request Info" button already has one; bottom "Reply Back" adds the second.
    assert content.count('data-target="#requestMoreInfoModal"') == 2
    assert "Reply Back" in content