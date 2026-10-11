# SPDX-License-Identifier: Apache-2.0
import dataclasses

from warehouse.admin.components.info_box import InfoBox


def test_info_box_props_are_a_dataclass():
    assert dataclasses.is_dataclass(InfoBox.Props)
    bound = InfoBox.Props(
        icon_bg="bg-info", icon="fa-bullhorn", text="Total Reports", number="42"
    )
    assert bound.subtext is None


def test_info_box_renders_minimal(env):
    template = env.from_string(
        '{% component "admin.info_box",'
        ' icon_bg="bg-info",'
        ' icon="fa-bullhorn",'
        ' text="Total Reports",'
        ' number="42" %}'
    )
    rendered = template.render()

    assert "info-box-icon bg-info" in rendered
    assert "fa-solid fa-bullhorn" in rendered
    assert "Total Reports" in rendered
    assert ">42<" in rendered
    assert "info-box-text small" not in rendered  # no subtext given


def test_info_box_renders_subtext(env):
    template = env.from_string(
        '{% component "admin.info_box",'
        ' icon_bg="bg-success",'
        ' icon="fa-check-double",'
        ' text="Corroborated Reports",'
        ' number="10",'
        ' subtext="packages with 2+ observers" %}'
    )
    rendered = template.render()

    assert "info-box-text small" in rendered
    assert "packages with 2+ observers" in rendered
