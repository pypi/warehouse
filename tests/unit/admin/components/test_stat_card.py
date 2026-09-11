# SPDX-License-Identifier: Apache-2.0
import dataclasses

from warehouse.admin.components.stat_card import StatCard


def test_stat_card_props_are_a_dataclass():
    assert dataclasses.is_dataclass(StatCard.Props)
    bound = StatCard.Props(color="bg-gradient-info", value="42 Approved")
    assert bound.icon == "fa-box"
    assert bound.sublines == []


def test_stat_card_renders_minimal(env):
    template = env.from_string(
        '{% component "admin.stat_card",'
        ' color="bg-gradient-info",'
        ' value="42 Approved" %}'
    )
    rendered = template.render()

    assert "small-box bg-gradient-info" in rendered
    assert "42 Approved" in rendered
    assert "fa-box" in rendered
    assert "small-box-footer" not in rendered  # no footer_url given
    assert "info-icon" not in rendered  # no tooltip given


def test_stat_card_renders_sublines_footer_and_tooltip(env):
    template = env.from_string(
        '{% component "admin.stat_card",'
        ' color="bg-gradient-teal",'
        ' value="5 With Projects",'
        ' sublines=["Community: 3", "Company: 2"],'
        ' icon="fa-folder-open",'
        ' footer_url="/admin/orgs",'
        ' footer_text="View All",'
        ' tooltip="Orgs with a project" %}'
    )
    rendered = template.render()

    assert "<h4>Community: 3</h4>" in rendered
    assert "<h4>Company: 2</h4>" in rendered
    assert 'href="/admin/orgs"' in rendered
    assert "View All" in rendered
    assert 'title="Orgs with a project"' in rendered
    assert "fa-solid fa-folder-open" in rendered


def test_stat_card_renders_description_paragraph(env):
    template = env.from_string(
        '{% component "admin.stat_card",'
        ' color="bg-gradient-warning",'
        ' value="3",'
        ' description="Open Malware Reports",'
        ' icon="fa-dumpster-fire" %}'
    )
    rendered = template.render()

    assert "<p>Open Malware Reports</p>" in rendered
