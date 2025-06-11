# SPDX-License-Identifier: Apache-2.0

import re

from pathlib import Path

import pytest

from jinja2 import Environment, FileSystemLoader

import warehouse

FILTERS = {
    "format_date": "warehouse.i18n.filters:format_date",
    "format_datetime": "warehouse.i18n.filters:format_datetime",
    "format_rfc822_datetime": "warehouse.i18n.filters:format_rfc822_datetime",
    "format_number": "warehouse.i18n.filters:format_number",
    "format_classifiers": "warehouse.filters:format_classifiers",
    "classifier_id": "warehouse.filters:classifier_id",
    "format_tags": "warehouse.filters:format_tags",
    "json": "warehouse.filters:tojson",
    "camoify": "warehouse.filters:camoify",
    "shorten_number": "warehouse.filters:shorten_number",
    "urlparse": "warehouse.filters:urlparse",
    "contains_valid_uris": "warehouse.filters:contains_valid_uris",
    "format_package_type": "warehouse.filters:format_package_type",
    "parse_version": "warehouse.filters:parse_version",
    "localize_datetime": "warehouse.filters:localize_datetime",
    "ctime": "warehouse.filters:ctime",
    "canonicalize_name": "packaging.utils:canonicalize_name",
}

# A compiled regex that matches a subject block, possibly with newlines inside
SUBJECT_BLOCK_EXPRESSION = re.compile(
    r"\{% block subject %}.*\{% endblock %}", re.DOTALL
)


@pytest.mark.parametrize(
    "template",
    [
        f.relative_to(Path(warehouse.__path__[0]) / "templates")
        for f in Path(warehouse.__path__[0]).glob("templates/**/*.html")
    ],
)
def test_templates_for_empty_titles(template: Path):
    """
    Test if all HTML templates have defined the title block. See
    https://github.com/pypi/warehouse/issues/784
    """
    dir_name = Path(warehouse.__path__[0]) / "templates"

    env = Environment(
        loader=FileSystemLoader(dir_name),
        extensions=[
            "jinja2.ext.i18n",
            "warehouse.utils.html.ClientSideIncludeExtension",
            "warehouse.i18n.extensions.TrimmedTranslatableTagsExtension",
        ],
        cache_size=0,
    )

    env.filters.update(FILTERS)

    if any(
        parent.name in ["includes", "api", "legacy", "email"]
        for parent in template.parents
    ):
        # Skips specific directories, which are not expected to have titles.
        return

    template_obj = env.get_template(str(template))
    assert "title" in template_obj.blocks or "title_base" in template_obj.blocks


@pytest.mark.parametrize(
    "template",
    [
        f.relative_to(Path(warehouse.__path__[0]) / "templates")
        for f in Path(warehouse.__path__[0]).glob("templates/**/*.html")
    ],
)
def test_render_templates(template):
    """
    Test if all HTML templates are rendered without Jinja exceptions.
    see https://github.com/pypi/warehouse/issues/6634
    """
    dir_name = Path(warehouse.__path__[0]) / "templates"

    env = Environment(
        loader=FileSystemLoader(dir_name),
        extensions=[
            "jinja2.ext.i18n",
            "warehouse.utils.html.ClientSideIncludeExtension",
            "warehouse.i18n.extensions.TrimmedTranslatableTagsExtension",
        ],
        cache_size=0,
    )

    env.filters.update(FILTERS)

    assert env.get_template(str(template))


@pytest.mark.parametrize(
    "template",
    [f for f in Path(warehouse.__path__[0]).glob("templates/email/**/subject.txt")],
)
def test_email_subjects_for_multiple_lines(template: Path):
    """
    Test if all email subject templates don't contain new lines. See
    https://github.com/pypi/warehouse/issues/13216
    """

    with template.open("r") as f:
        match = SUBJECT_BLOCK_EXPRESSION.search(f.read())
        # There should be a subject block inside a subject template file
        assert match is not None
        # There should NOT be a newline inside the subject block
        assert "\n" not in match.group(0)
